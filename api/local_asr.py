"""基于 sherpa-onnx + SenseVoice 的本地语音识别客户端。

音频先经 Silero VAD 切分为语音段，再用 SenseVoice 离线识别。
SenseVoice 自带标点，支持中/英/日/韩/粤；模块顶层不导入 sherpa_onnx。
"""

from __future__ import annotations

import queue
import re
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np

from utils.logger import logger

_INT8_MODEL = 'model.int8.onnx'
_FP32_MODEL = 'model.onnx'
_TOKENS = 'tokens.txt'
_VAD_MODEL = 'silero_vad.onnx'
_TAG_RE = re.compile(r'<\|[^|]*\|>')

_QUEUE_MAX_CHUNKS = 512          # 512 * 64ms ≈ 32 秒
_STOP_TIMEOUT_SECONDS = 5.0
_PARTIAL_INTERVAL = 1.5
_MAX_PARTIAL_SECONDS = 5.0
_VAD_THRESHOLD = 0.5
_VAD_WINDOW = 512
_VAD_MIN_SPEECH = 0.2
_VAD_MAX_SPEECH = 20.0
_SENTINEL = object()
_SUPPORTED_LANGUAGES = {'zh', 'en', 'ja', 'ko', 'yue'}


class LocalASRError(RuntimeError):
    """可直接展示给用户的本地引擎错误。"""


def _load_sherpa():
    """延迟导入，避免云端构建依赖 sherpa-onnx。"""
    import sherpa_onnx

    return sherpa_onnx


class LocalASRClient:
    """满足 RealtimeTranscriber 客户端契约的 SenseVoice 实现。

    VAD 负责断句，SenseVoice 负责识别；对外接口与 DashScopeASRClient 一致。
    """

    supports_reconnect = False

    def __init__(self, config, model_dir=None, num_threads=None):
        self.config = config
        self.last_error = ''

        self._sample_rate = int(getattr(config, 'sample_rate', 16000) or 16000)
        self._max_session_seconds = float(
            getattr(config, 'max_session_duration', 1200) or 1200
        )
        self._model_dir = Path(model_dir) if model_dir else None
        self._num_threads = num_threads

        self._lock = threading.RLock()
        self._vad_lock = threading.RLock()
        self._decode_lock = threading.RLock()
        self._queue: queue.Queue = queue.Queue(maxsize=_QUEUE_MAX_CHUNKS)
        self._callbacks = {}

        self._recognizer = None
        self._vad = None
        self._worker: Optional[threading.Thread] = None
        self._partial_thread: Optional[threading.Thread] = None
        self._partial_stop = threading.Event()

        self._started = False
        self._stopped = False
        self._stop_result: Optional[bool] = None
        self._interrupted = threading.Event()

        self._speech_active = False
        self._last_partial = ''
        self._decoded_seconds = 0.0
        self._final_texts = []

    # ------------------------------------------------------------------ 生命周期

    def start(
        self,
        on_partial=None,
        on_final=None,
        on_speech_start=None,
        on_speech_stop=None,
        on_error=None,
    ) -> bool:
        with self._lock:
            if self._started:
                return True
            if self._stopped:
                self.last_error = '本地识别客户端已停止，请重新开始录音。'
                return False

            try:
                self._validate_language()
                model_dir = self._resolve_model_dir()
                files = self._resolve_model_files(model_dir)
                sherpa = _load_sherpa()

                self._recognizer = sherpa.OfflineRecognizer.from_sense_voice(
                    model=str(files['model']),
                    tokens=str(files['tokens']),
                    num_threads=self._resolve_threads(),
                    sample_rate=self._sample_rate,
                    feature_dim=80,
                    decoding_method='greedy_search',
                    provider='cpu',
                    language=self._sense_voice_language(),
                    use_itn=True,
                    debug=False,
                )
                self._vad = self._build_vad(sherpa, files['vad'])

                self._callbacks = {
                    'on_partial': on_partial,
                    'on_final': on_final,
                    'on_speech_start': on_speech_start,
                    'on_speech_stop': on_speech_stop,
                    'on_error': on_error,
                }
                self._interrupted.clear()
                self._partial_stop.clear()
                self._started = True
                self._stopped = False
                self._stop_result = None

                self._worker = threading.Thread(
                    target=self._run, name='local-asr-worker', daemon=True
                )
                self._partial_thread = threading.Thread(
                    target=self._partial_loop, name='local-asr-partial', daemon=True
                )
                self._worker.start()
                self._partial_thread.start()
                logger.info(f'[LocalASR] 已启动（SenseVoice），模型目录: {model_dir}')
                return True

            except Exception as exc:
                self.last_error = self._friendly_error(exc)
                logger.exception(f'[LocalASR] 启动失败: {exc}')
                self._release()
                # 启动失败由 RealtimeTranscriber 统一上报，避免重复弹窗。
                return False

    def send_audio(self, audio_data: bytes) -> bool:
        with self._lock:
            if not self._started or self._stopped:
                return False
        try:
            self._queue.put_nowait(bytes(audio_data))
            return True
        except queue.Full:
            logger.warning('[LocalASR] 音频队列已满，丢弃当前音频块')
            return False

    def stop(self, timeout: int = 5) -> bool:
        """停止并冲刷最后一个语音段；幂等且有明确时限。"""
        with self._lock:
            if self._stopped:
                return True if self._stop_result is None else self._stop_result
            self._stopped = True
            self._started = False
            worker = self._worker

        limit = max(0.1, float(timeout or _STOP_TIMEOUT_SECONDS))
        deadline = time.monotonic() + limit
        self._partial_stop.set()

        if worker is None:
            self._release()
            self._stop_result = True
            return True

        try:
            self._queue.put(_SENTINEL, timeout=min(1.0, limit))
        except queue.Full:
            self._interrupted.set()
            try:
                self._queue.put(_SENTINEL, timeout=0.2)
            except queue.Full:
                pass

        if worker is not threading.current_thread():
            worker.join(max(0.0, deadline - time.monotonic()))

        if worker.is_alive():
            # 解码器可能卡在单个长段上；放弃剩余音频，保留已识别的文本。
            self._interrupted.set()
            worker.join(max(0.0, deadline - time.monotonic()))

        self._stop_result = not worker.is_alive()
        if not self._stop_result:
            self.last_error = '本地语音识别未能在时限内结束，最后一句可能未完整保存。'
            logger.error(f'[LocalASR] {self.last_error}')
        return self._stop_result

    def cancel_reconnect(self) -> None:
        """本地引擎没有重连流程；保持空实现以便停止流程统一调用。"""
        return None

    def interrupt(self) -> None:
        """丢弃尚未解码的音频，用于停止收尾超时。"""
        self._interrupted.set()
        self._partial_stop.set()

    # ------------------------------------------------------------------ 查询

    def is_connected(self) -> bool:
        return self._started and not self._stopped

    def get_transcription(self) -> str:
        with self._lock:
            return ' '.join(self._final_texts).strip()

    def get_current_partial(self) -> str:
        with self._lock:
            return self._last_partial

    def get_stats(self) -> dict:
        with self._lock:
            return {
                'provider': 'local',
                'engine': 'sensevoice',
                'is_connected': self.is_connected(),
                'final_segments': len(self._final_texts),
                'decoded_seconds': self._decoded_seconds,
                'queue_size': self._queue.qsize(),
            }

    # ------------------------------------------------------------------ 音频线程

    def _run(self) -> None:
        fatal: Optional[Exception] = None
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                break
            if self._interrupted.is_set():
                continue
            try:
                self._accept_chunk(item)
            except Exception as exc:
                fatal = exc
                self.last_error = self._friendly_error(exc)
                logger.exception(f'[LocalASR] 解码失败: {exc}')
                self._interrupted.set()
                break

        try:
            self._flush_vad()
        except Exception as exc:
            logger.exception(f'[LocalASR] 收尾失败: {exc}')
            if fatal is None:
                self.last_error = self._friendly_error(exc)
        finally:
            self._partial_stop.set()
            partial = self._partial_thread
            if partial is not None and partial is not threading.current_thread():
                partial.join(1.0)
            self._release()

        if fatal is not None:
            self._emit('on_error', fatal)

    def _accept_chunk(self, data: bytes) -> None:
        # S16LE 必须是偶数长度；异常块截断尾部而不是让解码线程崩溃。
        if len(data) % 2:
            data = data[:-1]
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            return

        segments = []
        with self._vad_lock:
            was_active = self._speech_active
            self._vad.accept_waveform(samples)
            active = self._vad.is_speech_detected()
            if active and not was_active:
                self._speech_active = True
                self._emit('on_speech_start')
            while not self._vad.empty():
                segment = self._vad.front
                segments.append(np.asarray(segment.samples, dtype=np.float32).copy())
                self._vad.pop()

        self._decoded_seconds += samples.size / float(self._sample_rate)
        for segment_samples in segments:
            self._finish_segment(segment_samples)

    def _finish_segment(self, samples) -> None:
        text = self._transcribe(samples)
        if self._speech_active:
            self._emit('on_speech_stop')
        if text:
            with self._lock:
                self._final_texts.append(text)
                self._last_partial = ''
            self._emit('on_final', text)
        self._speech_active = False

    def _flush_vad(self) -> None:
        if self._vad is None:
            return

        segments = []
        with self._vad_lock:
            self._vad.flush()
            while not self._vad.empty():
                segment = self._vad.front
                segments.append(np.asarray(segment.samples, dtype=np.float32).copy())
                self._vad.pop()

        for segment_samples in segments:
            self._finish_segment(segment_samples)

        if self._speech_active:
            self._emit('on_speech_stop')
            self._speech_active = False

    # ------------------------------------------------------------------ 中间结果

    def _partial_loop(self) -> None:
        while not self._partial_stop.wait(_PARTIAL_INTERVAL):
            try:
                self._emit_partial()
            except Exception as exc:
                logger.debug(f'[LocalASR] 中间结果解码失败: {exc}')

    def _emit_partial(self) -> None:
        with self._vad_lock:
            if self._vad is None or not self._vad.is_speech_detected():
                return
            segment = self._vad.current_segment
            samples = np.asarray(segment.samples, dtype=np.float32).copy()

        if samples.size == 0:
            return
        if samples.size / float(self._sample_rate) > _MAX_PARTIAL_SECONDS:
            return
        # 上一轮中间解码还没结束就跳过，避免占满 CPU。
        if not self._decode_lock.acquire(blocking=False):
            return
        try:
            text = self._transcribe_unlocked(samples)
        finally:
            self._decode_lock.release()

        if text and text != self._last_partial:
            with self._lock:
                self._last_partial = text
            self._emit('on_partial', text)

    # ------------------------------------------------------------------ 识别

    def _transcribe(self, samples) -> str:
        with self._decode_lock:
            return self._transcribe_unlocked(samples)

    def _transcribe_unlocked(self, samples) -> str:
        if samples is None or len(samples) == 0:
            return ''
        stream = self._recognizer.create_stream()
        stream.accept_waveform(self._sample_rate, samples)
        self._recognizer.decode_stream(stream)
        result = getattr(stream, 'result', None)
        return self._clean_text(getattr(result, 'text', ''))

    @staticmethod
    def _clean_text(text: str) -> str:
        # SenseVoice 会附带 <|zh|><|NEUTRAL|><|Speech|> 等标签。
        return _TAG_RE.sub('', text or '').strip()

    # ------------------------------------------------------------------ 辅助

    def _emit(self, name: str, *args) -> None:
        callback = (self._callbacks or {}).get(name)
        if not callback:
            return
        try:
            callback(*args)
        except Exception:
            logger.exception(f'[LocalASR] {name} 回调异常')

    def _release(self) -> None:
        self._vad = None
        self._recognizer = None

    def _validate_language(self) -> None:
        language = (getattr(self.config, 'language', 'zh') or 'zh').strip()
        if language not in _SUPPORTED_LANGUAGES:
            raise LocalASRError(
                f'本地版语音识别仅支持中文、英文、日语、韩语和粤语，'
                f'当前设置为“{language}”。请在设置中切换语言。'
            )

    def _sense_voice_language(self) -> str:
        language = (getattr(self.config, 'language', 'zh') or 'zh').strip()
        return language if language in _SUPPORTED_LANGUAGES else 'auto'

    def _resolve_model_dir(self) -> Path:
        if self._model_dir is not None:
            return self._model_dir
        from config.settings import get_local_asr_model_dir

        return get_local_asr_model_dir()

    def _resolve_model_files(self, model_dir: Path) -> dict:
        model = model_dir / _INT8_MODEL
        if not model.is_file():
            model = model_dir / _FP32_MODEL
        files = {
            'model': model,
            'tokens': model_dir / _TOKENS,
            'vad': model_dir / _VAD_MODEL,
        }
        missing = [path.name for path in files.values() if not path.is_file()]
        if missing:
            raise LocalASRError(
                f'本地 ASR 模型缺失：在 {model_dir} 下未找到 {", ".join(missing)}。\n'
                '请确认 models\\asr 与程序 exe 位于同一目录；'
                '如果是从压缩包运行，请先完整解压。'
            )
        return files

    def _build_vad(self, sherpa, vad_model_path: Path):
        silence = self._silence_seconds()
        silero = sherpa.SileroVadModelConfig(
            model=str(vad_model_path),
            threshold=_VAD_THRESHOLD,
            min_silence_duration=silence,
            min_speech_duration=_VAD_MIN_SPEECH,
            window_size=_VAD_WINDOW,
            max_speech_duration=_VAD_MAX_SPEECH,
        )
        config = sherpa.VadModelConfig(
            silero_vad=silero,
            sample_rate=self._sample_rate,
            num_threads=1,
            provider='cpu',
            debug=False,
        )
        return sherpa.VoiceActivityDetector(config, buffer_size_in_seconds=60)

    def _silence_seconds(self) -> float:
        vad_ms = float(getattr(self.config, 'vad_silence_ms', 400) or 400)
        return max(0.3, min(2.0, vad_ms / 1000.0))

    def _resolve_threads(self) -> int:
        if self._num_threads:
            return max(1, min(8, int(self._num_threads)))
        from config.settings import settings

        return max(1, min(8, int(settings.asr.local_num_threads)))

    def _friendly_error(self, error: Exception) -> str:
        if isinstance(error, LocalASRError):
            return str(error)
        if isinstance(error, ModuleNotFoundError) and 'sherpa' in str(error).lower():
            return (
                '本地 ASR 引擎未安装（缺少 sherpa-onnx）。'
                '请使用本地版安装包，或在源码环境安装 requirements-local.txt。'
            )
        if isinstance(error, ImportError):
            return '本地 ASR 引擎加载失败：缺少依赖。请使用本地版安装包。'
        if isinstance(error, MemoryError) or 'bad_alloc' in str(error).lower():
            return '本地语音识别模型加载失败：内存不足。请关闭其他程序后重试。'
        return f'本地语音识别启动失败：{error}'
