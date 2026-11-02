"""
DashScope 实时语音识别模块

基于 DashScope OmniRealtimeConversation 的实时语音识别封装。
支持 WebSocket 流式实时转录，适配中文语音识别场景。
支持自动分段轮替，可用于超长时间录音（超出单会话30分钟限制）。
"""

import base64
import struct
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional

# 添加项目根目录到Python路径（仅源码运行需要）
if not getattr(sys, 'frozen', False):
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

from dashscope.audio.qwen_omni import OmniRealtimeCallback, OmniRealtimeConversation, MultiModality
from dashscope.audio.qwen_omni.omni_realtime import TranscriptionParams

from config.settings import preview_asr_content, settings
from utils.exceptions import DashScopeAPIException
from utils.logger import logger
from utils.proxy import bypass_proxy_for, should_fallback_to_direct


def _install_tolerant_close_frame_parser() -> None:
    """允许解析超过 RFC 上限的 close 帧。

    DashScope 会把完整错误原因写进 close 帧，但长度常超过 125 字节。
    websocket-client 会因此丢弃该帧，调用方只能看到 "Invalid close frame"。
    这里仅放宽长度限制，close code 和 UTF-8 reason 仍然照常校验。
    """
    try:
        from websocket import _abnf
        from websocket._exceptions import WebSocketProtocolException
    except Exception:
        return
    if not hasattr(_abnf.ABNF, '_is_valid_close_status'):
        return
    original = _abnf.ABNF.validate
    if getattr(original, '_dashscope_long_close', False):
        return

    def validate(self, skip_utf8_validation: bool = False) -> None:
        if self.opcode == _abnf.ABNF.OPCODE_CLOSE:
            data = (self.data if isinstance(self.data, (bytes, bytearray))
                    else (self.data or '').encode('utf-8'))
            if len(data) > 125:
                if len(data) < 2:
                    raise WebSocketProtocolException('Invalid close frame.')
                code = struct.unpack('!H', data[:2])[0]
                if not self._is_valid_close_status(code):
                    raise WebSocketProtocolException(f'Invalid close opcode {code!r}')
                if len(data) > 2 and not skip_utf8_validation and not _abnf.validate_utf8(data[2:]):
                    raise WebSocketProtocolException('Invalid close frame.')
                return
        original(self, skip_utf8_validation)

    validate._dashscope_long_close = True  # type: ignore[attr-defined]
    _abnf.ABNF.validate = validate


def _describe_asr_close(code: Optional[int], message: Optional[str]) -> str:
    """把 WebSocket 关闭信息转换为用户可理解的提示。"""
    if isinstance(message, bytes):
        raw = message.decode('utf-8', errors='replace').strip()[:500]
    else:
        raw = (message or '').strip()[:500]
    lowered = raw.lower()
    if 'free tier' in lowered or 'quota' in lowered:
        return '语音识别服务失败：免费额度已耗尽。请在百炼控制台关闭“仅使用免费额度”模式，或充值后重试。'
    if code in (401, 403, 4001):
        return f'语音识别鉴权失败：{raw or "请检查 API Key 与业务空间配置。"}'
    if code == 1007:
        return f'语音识别服务拒绝了会话配置：{raw or "未知原因"}'
    if code is None:
        return '语音识别连接被服务端异常关闭（未返回原因）。常见原因：免费额度耗尽、API Key 权限不足或网络中断，请检查百炼控制台额度与 API 配置。'
    return f'语音识别连接已断开（code={code}）：{raw or "未知原因"}'


def _extract_transcript(response: dict) -> str:
    """兼容不同版本服务端的文本字段（新版流式文本在 stash）。"""
    for key in ('text', 'stash', 'transcript'):
        value = response.get(key)
        if value:
            return value
    content = response.get('content')
    return content if isinstance(content, str) else ''


def _describe_asr_connect_error(error: Exception) -> str:
    """把连接失败转换为用户可理解的提示。"""
    text = str(error)
    name = type(error).__name__
    if 'proxy' in text.lower() or 'proxy' in name.lower() or isinstance(error, ConnectionRefusedError):
        return (
            '无法通过系统代理连接语音识别服务。请检查代理/VPN 是否运行，'
            '或在设置中关闭“使用系统代理”后重试。'
        )
    return f'无法连接语音识别服务：{error}'


_install_tolerant_close_frame_parser()


@dataclass
class ASRResult:
    """语音识别结果"""
    text: str = ""                          # 识别文本
    is_partial: bool = False                # 是否为中间结果
    timestamp: float = field(default_factory=time.time)  # 时间戳
    audio_duration: float = 0.0             # 音频时长(秒)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "text": self.text,
            "is_partial": self.is_partial,
            "timestamp": self.timestamp,
            "audio_duration": self.audio_duration
        }


@dataclass
class ASRConfig:
    """语音识别配置"""
    # DashScope 配置
    api_key: str = ""                       # API Key
    model: str = "qwen3-asr-flash-realtime"  # 模型名称

    # WebSocket 配置（默认按地域/业务空间自动推导）
    base_url: str = field(default_factory=lambda: settings.api.ws_base_url)
    region: str = field(default_factory=lambda: settings.api.dashscope_region)

    # 音频配置
    sample_rate: int = 16000                # 采样率
    language: str = "zh"                    # 语言 (zh=中文)

    # VAD 配置
    enable_vad: bool = True                 # 启用语音活动检测
    vad_threshold: float = 0.0               # VAD 阈值
    vad_silence_ms: int = 400               # 静音检测时长(ms)

    # 自动分段配置（支持长时间录音）
    auto_rotate: bool = True                # 自动分段轮替，超出限制自动新建会话
    max_session_duration: float = 20 * 60   # 单个会话最大时长（秒），默认20分钟（留安全余量）
    rotate_on_silence: bool = True          # 在静音时轮替（避免打断说话中）

    # 自动重连配置（网络异常恢复）
    auto_reconnect: bool = True             # 是否启用自动重连
    max_reconnect_attempts: int = 3         # 最大重连尝试次数
    reconnect_delay: float = 1.0            # 重连延迟（秒），使用指数退避

    # 回调配置
    on_partial_result: Optional[Callable[[str], None]] = None
    on_final_result: Optional[Callable[[str], None]] = None
    on_error: Optional[Callable[[Exception], None]] = None


class RealtimeASRCallback(OmniRealtimeCallback):
    """
    DashScope 实时语音识别回调处理

    处理服务端返回的各类事件，包括：
    - 会话创建/更新
    - 语音活动检测（VAD）
    - 中间识别结果（实时显示）
    - 最终识别结果（整句完成）
    """

    def __init__(
        self,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
        on_speech_start: Optional[Callable] = None,
        on_speech_stop: Optional[Callable] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        super().__init__()

        # 回调函数
        self.on_partial = on_partial
        self.on_final = on_final
        self.on_speech_start = on_speech_start
        self.on_speech_stop = on_speech_stop
        self.on_error = on_error

        # 状态管理
        self.conversation: Optional[OmniRealtimeConversation] = None
        self.is_connected = False
        self.session_id: Optional[str] = None
        self._intentional_close = False
        self._error_reported = False

        # 结果收集（当前会话）
        self.full_transcription = ""
        self.current_partial = ""

        # 统计信息
        self.speech_start_time: Optional[float] = None
        self.total_speech_duration = 0.0
        self.session_start_time: float = time.time()

        logger.debug("RealtimeASRCallback 初始化完成")

    def set_conversation(self, conversation: OmniRealtimeConversation):
        """注入conversation实例，用于控制会话"""
        self.conversation = conversation

    def on_open(self):
        """WebSocket连接成功建立"""
        logger.info("[ASR] WebSocket连接已建立")
        self.is_connected = True
        self.session_start_time = time.time()

    def mark_intentional_close(self) -> None:
        """标记主动关闭，避免把正常停止误报为异常。"""
        self._intentional_close = True

    def on_close(self, code: Optional[int], msg: Optional[str]):
        """WebSocket连接关闭"""
        self.is_connected = False
        if self._intentional_close:
            logger.info(f"[ASR] WebSocket连接已关闭, code: {code}, msg: {msg}")
            return
        logger.warning(f"[ASR] WebSocket连接被服务端关闭, code: {code}, msg: {msg}")
        if self.on_error and not self._error_reported:
            self._error_reported = True
            self.on_error(DashScopeAPIException(
                _describe_asr_close(code, msg),
                error_code='ASR_CONNECTION_CLOSED',
                status_code=code if isinstance(code, int) else None,
            ))

    def on_event(self, response: dict):
        """
        处理服务端事件

        主要处理的事件类型：
        - session.created: 会话创建
        - session.updated: 会话更新
        - input_audio_buffer.speech_started: 开始说话
        - input_audio_buffer.speech_stopped: 停止说话
        - conversation.item.input_audio_transcription.text: 中间结果
        - conversation.item.input_audio_transcription.completed: 最终结果
        """
        try:
            event_type = response.get('type', '')
            logger.trace(f"[ASR] 收到事件: {event_type}")

            # 会话创建
            if event_type == 'session.created':
                self.session_id = response.get('session', {}).get('id')
                logger.info(f"[ASR] 会话已创建: {self.session_id}")

            # 会话更新
            elif event_type == 'session.updated':
                logger.debug(f"[ASR] 会话配置已更新: {response.get('session', {})}")

            # VAD检测到语音开始
            elif event_type == 'input_audio_buffer.speech_started':
                self.speech_start_time = time.time()
                logger.info("[ASR] 检测到语音开始")
                if self.on_speech_start:
                    self.on_speech_start()

            # VAD检测到语音结束
            elif event_type == 'input_audio_buffer.speech_stopped':
                if self.speech_start_time:
                    duration = time.time() - self.speech_start_time
                    self.total_speech_duration += duration
                    logger.info(f"[ASR] 检测到语音结束, 时长: {duration:.2f}s")
                if self.on_speech_stop:
                    self.on_speech_stop()

            # 中间识别结果：兼容 text/stash 字段
            elif event_type == 'conversation.item.input_audio_transcription.text':
                text = _extract_transcript(response)
                if text:
                    self.current_partial = text
                    logger.debug(f"[ASR] 中间结果: {preview_asr_content(text)}")
                    if self.on_partial:
                        self.on_partial(text)

            # 最终识别结果：兼容 transcript 字段
            elif event_type == 'conversation.item.input_audio_transcription.completed':
                text = _extract_transcript(response)
                if text:
                    self.full_transcription += text + " "
                    self.current_partial = ""
                    logger.info(f"[ASR] 最终结果: {preview_asr_content(text)}")
                    if self.on_final:
                        self.on_final(text)

            # 会话完成
            elif event_type == 'session.finished':
                logger.info("[ASR] 会话已完成")

            # 错误
            elif event_type == 'error':
                error = response.get('error', {})
                error_msg = error.get('message', 'Unknown error')
                logger.error(f"[ASR] 服务端错误: {error_msg}")
                if self.on_error and not self._error_reported:
                    self._error_reported = True
                    self.on_error(DashScopeAPIException(
                        f'语音识别服务错误：{error_msg}',
                        error_code=str(error.get('code') or 'ASR_SERVER_ERROR'),
                    ))

            else:
                logger.debug(f"[ASR] 未处理的事件类型: {event_type}")

        except Exception as e:
            logger.exception(f"[ASR] 处理事件时出错: {e}")
            if self.on_error:
                self.on_error(e)

    def get_session_duration(self) -> float:
        """获取当前会话时长"""
        return time.time() - self.session_start_time

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "session_id": self.session_id,
            "is_connected": self.is_connected,
            "total_speech_duration": self.total_speech_duration,
            "full_transcription_length": len(self.full_transcription),
            "session_duration": self.get_session_duration()
        }


class DashScopeASRClient:
    """
    DashScope 实时语音识别客户端

    封装 OmniRealtimeConversation 的 WebSocket 连接管理。
    支持自动会话轮替，可处理超长时间录音。
    """

    def __init__(self, config: ASRConfig):
        self.config = config
        self._lock = threading.RLock()  # 使用可重入锁，避免嵌套获取时死锁

        # 当前活动会话
        self.conversation: Optional[OmniRealtimeConversation] = None
        self.callback: Optional[RealtimeASRCallback] = None

        # 累积所有会话的完整转录
        self._full_transcription_total: str = ""

        # 状态
        self.is_running = False
        self._is_speaking: bool = False
        self._last_speech_end_time: Optional[float] = None

        # 重连状态
        self._reconnect_count: int = 0  # 当前重连次数
        self._reconnect_lock = threading.Lock()  # 避免并发重连

        # 保存回调参数用于重连
        self._cached_callbacks: Optional[tuple] = None

        # 最近一次连接失败原因
        self.last_error: str = ''

        # 背景线程用于检查是否需要轮替
        self._rotate_check_thread: Optional[threading.Thread] = None
        self._stop_rotate_check = threading.Event()
        self._cancel_reconnect = threading.Event()

        logger.info("[ASR] DashScopeASRClient 初始化完成")

    def start(self,
              on_partial: Optional[Callable[[str], None]] = None,
              on_final: Optional[Callable[[str], None]] = None,
              on_speech_start: Optional[Callable] = None,
              on_speech_stop: Optional[Callable] = None,
              on_error: Optional[Callable[[Exception], None]] = None) -> bool:
        """
        启动实时语音识别

        Args:
            on_partial: 中间结果回调
            on_final: 最终结果回调
            on_speech_start: 语音开始回调
            on_speech_stop: 语音结束回调
            on_error: 错误回调

        Returns:
            是否启动成功
        """
        # 启动前校验 API Key，避免建立无效连接。
        if not self.config.api_key or self.config.api_key.strip() == "":
            logger.error("[ASR] API Key未配置，请设置有效的DashScope API Key")
            self.last_error = "API Key 未配置，请在设置中填写有效的 DashScope API Key。"
            if on_error:
                on_error(ValueError(self.last_error))
            return False

        try:
            self._full_transcription_total = ""
            self._is_speaking = False
            self._last_speech_end_time = None
            self._reconnect_count = 0
            self._stop_rotate_check.clear()
            self._cancel_reconnect.clear()

            # 保存回调参数用于后续重连
            self._cached_callbacks_save(on_partial, on_final, on_speech_start, on_speech_stop, on_error)

            # 创建第一个会话
            success = self._create_new_session(on_partial, on_final, on_speech_start, on_speech_stop, on_error)
            if not success:
                return False

            self.is_running = True

            # 启动背景检查线程（如果启用自动轮替）
            if self.config.auto_rotate:
                self._rotate_check_thread = threading.Thread(
                    target=self._rotate_check_loop,
                    args=(on_partial, on_final, on_speech_start, on_speech_stop, on_error),
                    daemon=True
                )
                self._rotate_check_thread.start()
                logger.info("[ASR] 自动轮替检查已启动")

            logger.info("[ASR] DashScope 实时语音识别服务已启动")
            return True

        except Exception as e:
            logger.exception(f"[ASR] 启动失败: {e}")
            self.is_running = False
            self.last_error = _describe_asr_connect_error(e)
            if on_error:
                on_error(e)
            return False

    def _create_new_session(
        self,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
        on_speech_start: Optional[Callable] = None,
        on_speech_stop: Optional[Callable] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ) -> bool:
        """创建新的会话"""
        with self._lock:
            try:
                if self._stop_rotate_check.is_set():
                    return False
                if self.conversation:
                    if self.callback:
                        self.callback.mark_intentional_close()
                    self.conversation.close()
                # 轮替前合并已有会话的文本。
                if self.callback:
                    # 已完成句子与未完成句尾都要保留，避免轮替丢字。
                    accumulated = self.callback.full_transcription
                    if self.callback.current_partial:
                        accumulated += self.callback.current_partial + " "
                        # 保留被轮替/重连中断的句尾，避免下一会话覆盖临时文字。
                        if on_final:
                            on_final(self.callback.current_partial)
                        self.callback.current_partial = ''
                    self._full_transcription_total += accumulated
                    logger.info(f"[ASR] 会话轮替：累积 {len(self._full_transcription_total)} 字符")

                # 创建回调与对话实例
                self.callback = self._build_callback(
                    on_partial, on_final, on_speech_start, on_speech_stop, on_error)
                self.conversation = self._build_conversation(self.callback)
                self.callback.set_conversation(self.conversation)

                # 建立 WebSocket 连接（本机代理失效时自动直连重试）
                self._connect_with_proxy_fallback(
                    on_partial, on_final, on_speech_start, on_speech_stop, on_error)
                if self._stop_rotate_check.is_set():
                    self.conversation.close()
                    return False

                # 配置会话参数
                transcription_params = TranscriptionParams(
                    language=self.config.language,
                    sample_rate=self.config.sample_rate,
                    input_audio_format="pcm"
                )

                self.conversation.update_session(
                    output_modalities=[MultiModality.TEXT],
                    enable_turn_detection=self.config.enable_vad,
                    turn_detection_type="server_vad",
                    turn_detection_threshold=self.config.vad_threshold,
                    turn_detection_silence_duration_ms=self.config.vad_silence_ms,
                    enable_input_audio_transcription=True,
                    transcription_params=transcription_params
                )

                logger.info(f"[ASR] 新会话创建成功: {self.callback.session_id}")
                return True

            except Exception as e:
                logger.exception(f"[ASR] 创建新会话失败: {e}")
                self.last_error = _describe_asr_connect_error(e)
                return False

    def _build_callback(
        self,
        on_partial: Optional[Callable[[str], None]],
        on_final: Optional[Callable[[str], None]],
        on_speech_start: Optional[Callable],
        on_speech_stop: Optional[Callable],
        on_error: Optional[Callable[[Exception], None]],
    ) -> RealtimeASRCallback:
        """创建带包装的回调实例。"""
        return RealtimeASRCallback(
            on_partial=on_partial,
            on_final=self._wrap_final_callback(on_final),
            on_speech_start=self._wrap_speech_start(on_speech_start),
            on_speech_stop=self._wrap_speech_end(on_speech_stop),
            on_error=on_error,
        )

    def _build_conversation(self, callback: RealtimeASRCallback) -> OmniRealtimeConversation:
        """创建对话实例。"""
        return OmniRealtimeConversation(
            model=self.config.model,
            callback=callback,
            url=self.config.base_url,
            api_key=self.config.api_key,
        )

    def _connect_with_proxy_fallback(
        self,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
        on_speech_start: Optional[Callable] = None,
        on_speech_stop: Optional[Callable] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """建立连接；系统代理为本机且失效时，改用直连重试一次。"""
        logger.info("[ASR] 正在连接 DashScope 实时语音识别服务...")
        try:
            self.conversation.connect()
            return
        except Exception as exc:
            if not should_fallback_to_direct(self.config.base_url, settings.api.proxy_mode):
                raise
            logger.warning(f"[ASR] 系统代理不可用（{exc}），改用直连重试")
            # 先标记主动关闭，避免旧连接延迟回调被误报为异常。
            if self.callback:
                self.callback.mark_intentional_close()
            host = urllib.parse.urlparse(self.config.base_url).hostname or ''
            with bypass_proxy_for([host]):
                self.callback = self._build_callback(
                    on_partial, on_final, on_speech_start, on_speech_stop, on_error)
                self.conversation = self._build_conversation(self.callback)
                self.callback.set_conversation(self.conversation)
                self.conversation.connect()

    def _wrap_final_callback(self, on_final: Optional[Callable[[str], None]]) -> Optional[Callable[[str], None]]:
        """包装最终结果回调，保证原始回调被调用"""
        if not on_final:
            return None

        def wrapped(text: str):
            # 包装层只转发文本，累积由 RealtimeTranscriber 负责。
            on_final(text)
        return wrapped

    def _wrap_speech_start(self, on_speech_start: Optional[Callable]) -> Optional[Callable]:
        """包装语音开始回调，跟踪说话状态"""
        if not on_speech_start:
            return None

        def wrapped():
            self._is_speaking = True
            self._last_speech_end_time = None
            if on_speech_start:
                on_speech_start()
        return wrapped

    def _wrap_speech_end(self, on_speech_stop: Optional[Callable]) -> Optional[Callable]:
        """包装语音结束回调，跟踪说话状态"""
        if not on_speech_stop:
            return None

        def wrapped():
            self._is_speaking = False
            self._last_speech_end_time = time.time()
            if on_speech_stop:
                on_speech_stop()
        return wrapped

    def _rotate_check_loop(
        self,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
        on_speech_start: Optional[Callable] = None,
        on_speech_stop: Optional[Callable] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        """背景循环检查是否需要轮替会话"""
        while not self._stop_rotate_check.is_set():
            if self._stop_rotate_check.wait(5):
                break
            if not self.is_running:
                break

            with self._lock:
                if not self.config.auto_rotate or not self.callback:
                    continue

                # 检查是否超过最大会话时长
                session_duration = self.callback.get_session_duration()
                need_rotate = session_duration >= self.config.max_session_duration

                # 超过时长后等待静音再轮替，避免打断说话。
                if need_rotate and self.config.rotate_on_silence:
                    if not self._is_speaking and self._last_speech_end_time:
                        silence_duration = time.time() - self._last_speech_end_time
                        if silence_duration > 2.0:  # 静音超过2秒才轮替
                            logger.info(f"[ASR] 自动轮替：会话时长 {session_duration:.1f}s 超出限制，当前静音 {silence_duration:.1f}s，创建新会话")
                            self._rotate_session(on_partial, on_final, on_speech_start, on_speech_stop, on_error)
                elif need_rotate:
                    # 不要求静音，直接轮替
                    logger.info(f"[ASR] 自动轮替：会话时长 {session_duration:.1f}s 超出限制，创建新会话")
                    self._rotate_session(on_partial, on_final, on_speech_start, on_speech_stop, on_error)

    def _rotate_session(
        self,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
        on_speech_start: Optional[Callable] = None,
        on_speech_stop: Optional[Callable] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        """轮替会话：结束当前会话，创建新会话"""
        if not self._reconnect_lock.acquire(blocking=False):
            return
        try:
            if self._stop_rotate_check.is_set():
                return
            try:
                # 关闭连接可能阻塞，必须在锁外执行。
                conversation_to_close = None
                with self._lock:
                    conversation_to_close = self.conversation

                if conversation_to_close:
                    if self.callback:
                        self.callback.mark_intentional_close()
                    try:
                        conversation_to_close.end_session(timeout=5)
                    except Exception as e:
                        logger.debug(f"[ASR] 结束旧会话超时: {e}，继续关闭连接")
                    try:
                        conversation_to_close.close()
                    except Exception as e:
                        logger.debug(f"[ASR] 关闭旧连接出错: {e}")

                # 创建新会话（_create_new_session 内部会自己拿锁）
                success = self._create_new_session(on_partial, on_final, on_speech_start, on_speech_stop, on_error)
                if not success:
                    logger.error("[ASR] 会话轮替失败，新会话创建失败，请检查网络连接和API配置")
            except Exception as e:
                logger.exception(f"[ASR] 会话轮替出错: {e}")
                if on_error:
                    on_error(e)
        finally:
            self._reconnect_lock.release()

    def send_audio(self, audio_data: bytes) -> bool:
        """
        发送音频数据到服务端

        Args:
            audio_data: PCM 格式的音频数据

        Returns:
            是否发送成功
        """
        if not self.is_running or not self.conversation:
            logger.warning("[ASR] 客户端未运行，无法发送音频")
            return False

        try:
            # 将音频数据编码为 Base64
            audio_b64 = base64.b64encode(audio_data).decode('utf-8')

            # 发送音频数据
            self.conversation.append_audio(audio_b64)

            # 发送成功，重置重连计数
            if self._reconnect_count > 0:
                logger.debug("[ASR] 发送成功，重置重连计数")
                self._reconnect_count = 0

            return True

        except Exception as e:
            logger.warning(f"[ASR] 发送音频数据失败: {e}")

            # 尝试自动重连
            if self.config.auto_reconnect and self._try_reconnect():
                # 重连成功，重试发送
                try:
                    audio_b64 = base64.b64encode(audio_data).decode('utf-8')
                    self.conversation.append_audio(audio_b64)
                    logger.info("[ASR] 重连成功，已恢复发送")
                    return True
                except Exception as retry_e:
                    logger.error(f"[ASR] 重连后发送仍然失败: {retry_e}")

            return False

    def _try_reconnect(self) -> bool:
        """
        尝试自动重连

        Returns:
            是否重连成功
        """
        # 防止并发重连
        if not self._reconnect_lock.acquire(blocking=False):
            logger.debug("[ASR] 已有重连在进行中，跳过")
            return False

        try:
            if self._cancel_reconnect.is_set():
                return False
            # 检查是否超过最大重连次数
            if self._reconnect_count >= self.config.max_reconnect_attempts:
                logger.error(f"[ASR] 已达到最大重连次数 {self.config.max_reconnect_attempts}，停止重连")
                return False

            # 递增重连计数
            self._reconnect_count += 1
            attempt = self._reconnect_count
            delay = self.config.reconnect_delay * (2 ** (attempt - 1))  # 指数退避

            logger.warning(f"[ASR] 尝试第 {attempt}/{self.config.max_reconnect_attempts} 次重连，等待 {delay:.1f} 秒")
            if self._cancel_reconnect.wait(delay):
                return False

            # 使用缓存的回调创建新会话
            if not self._cached_callbacks:
                logger.error("[ASR] 没有缓存的回调信息，无法重连")
                return False

            on_partial, on_final, on_speech_start, on_speech_stop, on_error = self._cached_callbacks

            # 保存当前累积的文本
            # _create_new_session 会自动合并到 _full_transcription_total
            success = self._create_new_session(on_partial, on_final, on_speech_start, on_speech_stop, on_error)

            if success:
                logger.info(f"[ASR] 第 {attempt} 次重连成功")
                return True
            else:
                logger.error(f"[ASR] 第 {attempt} 次重连失败")
                return False

        finally:
            self._reconnect_lock.release()

    def _cached_callbacks_save(self, on_partial, on_final, on_speech_start, on_speech_stop, on_error):
        """保存回调参数用于重连"""
        self._cached_callbacks = (on_partial, on_final, on_speech_start, on_speech_stop, on_error)

    def cancel_reconnect(self):
        """停止时取消退避等待，仍允许发送已缓冲的音频。"""
        self._cancel_reconnect.set()

    def interrupt(self):
        """强制打断阻塞的网络发送，仅用于停止收尾超时。"""
        self._cancel_reconnect.set()
        self._stop_rotate_check.set()
        conversation = self.conversation
        if conversation:
            if self.callback:
                self.callback.mark_intentional_close()
            conversation.close()

    def stop(self, timeout: int = 5) -> bool:
        """
        停止实时语音识别

        Args:
            timeout: 等待会话结束的超时时间（秒）
              短超时更好：因为我们已经在录音过程中实时累积了所有文本，
              不需要等服务端返回最终结果，超时不影响已累积的文本。

        Returns:
            是否停止成功
        """
        if not self.is_running and not self.conversation:
            logger.warning("[ASR] 客户端未运行")
            return True

        try:
            # 停止轮替检查线程（短超时，不需要等太久）
            self._stop_rotate_check.set()
            self._cancel_reconnect.set()
            if (self._rotate_check_thread and self._rotate_check_thread.is_alive()
                    and self._rotate_check_thread is not threading.current_thread()):
                self._rotate_check_thread.join()

            logger.info("[ASR] 正在停止实时语音识别...")

            # 在锁内读取会话引用，在锁外关闭连接。
            conversation_to_close = None
            with self._lock:
                conversation_to_close = self.conversation

            if conversation_to_close:
                if self.callback:
                    self.callback.mark_intentional_close()
                # 尝试优雅结束会话，但即使超时也要继续关闭连接
                # end_session 可能会阻塞（等待服务端响应），必须放在锁外
                try:
                    conversation_to_close.end_session(timeout=timeout)
                except Exception as e:
                    logger.warning(f"[ASR] end_session 超时或失败: {e}，继续关闭连接")
                # 无论如何都要关闭连接
                try:
                    conversation_to_close.close()
                except Exception as e:
                    logger.warning(f"[ASR] 关闭连接时出错: {e}")

            with self._lock:
                self.is_running = False
                # 清空所有缓存引用，帮助垃圾回收
                # 合并结束过程中到达的最终结果。
                if self.callback:
                    self._full_transcription_total += self.callback.full_transcription
                    self._full_transcription_total += self.callback.current_partial
                self.conversation = None
                self.callback = None
                self._cached_callbacks = None
                self._reconnect_count = 0

            logger.info(f"[ASR] 实时语音识别已停止，总转录长度: {len(self.get_transcription())}")
            return True

        except Exception as e:
            logger.exception(f"[ASR] 停止失败: {e}")
            self.is_running = False
            # 即使失败也要清空引用
            with self._lock:
                self.conversation = None
                self.callback = None
                self._cached_callbacks = None
            return False

    def is_connected(self) -> bool:
        """检查是否已连接到服务端"""
        return self.callback is not None and self.callback.is_connected

    def get_transcription(self) -> str:
        """获取当前完整转录文本（所有会话合并）"""
        with self._lock:
            total = self._full_transcription_total
            if self.callback:
                # 加上已完成句子
                total += self.callback.full_transcription
                # 合并未完成句尾，避免停止时丢失最后一段文本。
                if self.callback.current_partial:
                    total += self.callback.current_partial
            return total.strip()

    def get_current_partial(self) -> str:
        """获取当前会话的中间结果"""
        with self._lock:
            if self.callback:
                return self.callback.current_partial
            return ""

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            stats = {}
            if self.callback:
                stats = self.callback.get_stats()
            stats['total_length'] = len(self.get_transcription())
            stats['accumulated_length'] = len(self._full_transcription_total)
            return stats
