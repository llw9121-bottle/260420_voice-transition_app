"""基于 sherpa-onnx 的本地流式语音识别客户端。

模块顶层不导入 sherpa_onnx：云端构建和离线测试不要求安装本地引擎。
"""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np

from utils.logger import logger

_INT8_FILES = ('encoder.int8.onnx', 'decoder.int8.onnx', 'tokens.txt')
_FP32_FILES = ('encoder.onnx', 'decoder.onnx', 'tokens.txt')
_SPEECH_RMS_THRESHOLD = 0.008
_QUEUE_MAX_CHUNKS = 512          # 512 * 64ms ≈ 32 秒
_STOP_TIMEOUT_SECONDS = 5.0
_SENTINEL = object()


class LocalASRError(RuntimeError):
    """可直接展示给用户的本地引擎错误。"""


def _load_sherpa():
    """延迟导入，避免云端构建依赖 sherpa-onnx。"""
    import sherpa_onnx

    return sherpa_onnx


class LocalASRClient:
    """满足 RealtimeTranscriber 客户端契约的本地实现。

    对外接口与 DashScopeASRClient 保持一致；不支持网络重连。
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
        self._queue: queue.Queue = queue.Queue(maxsize=_QUEUE_MAX_CHUNKS)
        self._callbacks = {}

        self._recognizer = None
        self._stream = None
        self._worker: Optional[threading.Thread] = None

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
                silence = self._endpoint_silence_seconds()

                self._recognizer = sherpa.OnlineRecognizer.from_paraformer(
                    tokens=str(files['tokens']),
                    encoder=str(files['encoder']),
                    decoder=str(files['decoder']),
                    num_threads=self._resolve_threads(),
                    sample_rate=self._sample_rate,
                    feature_dim=80,
                    decoding_method='greedy_search',
                    enable_endpoint_detection=True,
                    rule1_min_trailing_silence=max(2.4, silence * 2),
                    rule2_min_trailing_silence=silence,
                    rule3_min_utterance_length=20.0,
                    provider='cpu',
                    debug=False,
                )
                self._stream = self._recognizer.create_stream()
                self._callbacks = {
                    'on_partial': on_partial,
                    'on_final': on_final,
                    'on_speech_start': on_speech_start,
                    'on_speech_stop': on_speech_stop,
                    'on_error': on_error,
                }
                self._interrupted.clear()
                self._started = True
                self._stopped = False
                self._stop_result = None

                self._worker = threading.Thread(
                    target=self._run, name='local-asr-worker', daemon=True
                )
                self._worker.start()
                logger.info(f'[LocalASR] 已启动，模型目录: {model_dir}')
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
        """停止并冲刷最后一句；幂等且有明确时限。"""
        with self._lock:
            if self._stopped:
                return True if self._stop_result is None else self._stop_result
            self._stopped = True
            self._started = False
            worker = self._worker

        if worker is None:
            self._release()
            self._stop_result = True
            return True

        limit = max(0.1, float(timeout or _STOP_TIMEOUT_SECONDS))
        deadline = time.monotonic() + limit

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
            # 解码器可能卡在单个长块上；放弃剩余音频，保留已识别的文本。
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
                'is_connected': self.is_connected(),
                'final_segments': len(self._final_texts),
                'decoded_seconds': self._decoded_seconds,
                'queue_size': self._queue.qsize(),
            }

    # ------------------------------------------------------------------ 解码线程

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
            self._flush_final()
        except Exception as exc:
            logger.exception(f'[LocalASR] 收尾失败: {exc}')
            if fatal is None:
                self.last_error = self._friendly_error(exc)
        finally:
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

        rms = float(np.sqrt(np.mean(np.square(samples))))
        if rms >= _SPEECH_RMS_THRESHOLD and not self._speech_active:
            self._speech_active = True
            self._emit('on_speech_start')

        self._stream.accept_waveform(self._sample_rate, samples)
        while self._recognizer.is_ready(self._stream):
            self._recognizer.decode_stream(self._stream)

        text = self._current_text()
        if text and text != self._last_partial:
            with self._lock:
                self._last_partial = text
            self._emit('on_partial', text)

        self._decoded_seconds += samples.size / float(self._sample_rate)

        if self._recognizer.is_endpoint(self._stream):
            self._finish_endpoint()
        elif self._decoded_seconds >= self._max_session_seconds:
            # 连续说话可能长时间不触发 endpoint，主动收一段避免状态无限增长。
            self._finish_endpoint()

    def _finish_endpoint(self) -> None:
        if self._recognizer is None or self._stream is None:
            return

        while self._recognizer.is_ready(self._stream):
            self._recognizer.decode_stream(self._stream)

        text = self._current_text()
        if self._speech_active:
            self._emit('on_speech_stop')
        if text:
            with self._lock:
                self._final_texts.append(text)
                self._last_partial = ''
            self._emit('on_final', text)

        self._recognizer.reset(self._stream)
        self._speech_active = False
        self._decoded_seconds = 0.0

    def _flush_final(self) -> None:
        if self._recognizer is None or self._stream is None:
            return

        tail = np.zeros(int(self._sample_rate * 0.3), dtype=np.float32)
        self._stream.accept_waveform(self._sample_rate, tail)
        if hasattr(self._stream, 'input_finished'):
            self._stream.input_finished()

        while self._recognizer.is_ready(self._stream):
            self._recognizer.decode_stream(self._stream)

        text = self._current_text()
        if self._speech_active:
            self._emit('on_speech_stop')
        if text:
            with self._lock:
                self._final_texts.append(text)
                self._last_partial = ''
            self._emit('on_final', text)

        self._speech_active = False

    # ------------------------------------------------------------------ 辅助

    def _current_text(self) -> str:
        if self._recognizer is None or self._stream is None:
            return ''
        try:
            result = self._recognizer.get_result(self._stream)
        except Exception:
            return ''
        # sherpa-onnx 2.x 返回 str；旧版本/其他封装可能返回带 text 的对象。
        if isinstance(result, str):
            return result.strip()
        return (getattr(result, 'text', '') or '').strip()

    def _emit(self, name: str, *args) -> None:
        callback = (self._callbacks or {}).get(name)
        if not callback:
            return
        try:
            callback(*args)
        except Exception:
            logger.exception(f'[LocalASR] {name} 回调异常')

    def _release(self) -> None:
        self._stream = None
        self._recognizer = None

    def _validate_language(self) -> None:
        language = (getattr(self.config, 'language', 'zh') or 'zh').strip()
        if language not in ('zh', 'en'):
            raise LocalASRError(
                f'本地版语音识别仅支持中文（zh）和英文（en），'
                f'当前设置为“{language}”。请在设置中切换语言。'
            )

    def _resolve_model_dir(self) -> Path:
        if self._model_dir is not None:
            return self._model_dir
        from config.settings import get_local_asr_model_dir

        return get_local_asr_model_dir()

    def _resolve_model_files(self, model_dir: Path) -> dict:
        for names in (_INT8_FILES, _FP32_FILES):
            paths = {
                'encoder': model_dir / names[0],
                'decoder': model_dir / names[1],
                'tokens': model_dir / names[2],
            }
            if all(path.is_file() for path in paths.values()):
                return paths

        expected = ' / '.join(_INT8_FILES)
        raise LocalASRError(
            f'本地 ASR 模型缺失：在 {model_dir} 下未找到 {expected}。\n'
            '请确认 models\\asr 与程序 exe 位于同一目录；'
            '如果是从压缩包运行，请先完整解压。'
        )

    def _endpoint_silence_seconds(self) -> float:
        vad_ms = float(getattr(self.config, 'vad_silence_ms', 400) or 400)
        return max(0.6, min(3.0, vad_ms / 1000.0))

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
