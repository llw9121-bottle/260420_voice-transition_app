"""
实时转录器模块

整合 PyAudio 录音 + DashScope 实时语音识别，实现边说边转录的完整功能。

功能：
- 实时音频流捕获
- WebSocket 流式识别
- 实时结果显示（中间结果 + 最终结果）
- 会话管理和资源清理
"""

import io
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, List

# 设置标准输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.audio_recorder import AudioRecorder, AudioConfig
from api.dashscope_asr import DashScopeASRClient, ASRConfig, ASRResult
from utils.logger import logger


@dataclass
class TranscriberState:
    """转录器状态"""
    is_recording: bool = False
    is_connected: bool = False
    start_time: Optional[float] = None
    audio_duration: float = 0.0
    
    def reset(self):
        """重置状态"""
        self.is_recording = False
        self.is_connected = False
        self.start_time = None
        self.audio_duration = 0.0


@dataclass
class TranscriptionResult:
    """转录结果"""
    full_text: str = ""
    partial_text: str = ""
    is_final: bool = False
    timestamp: float = 0.0


class RealtimeTranscriber:
    """
    实时转录器
    
    整合音频录制和实时语音识别，提供简单易用的实时转录接口。
    
    使用示例：
        transcriber = RealtimeTranscriber()
        
        def on_text(text, is_final):
            if is_final:
                print(f"最终: {text}")
            else:
                print(f"中间: {text}")
        
        transcriber.start(on_text=on_text)
        time.sleep(10)  # 录制10秒
        transcriber.stop()
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        sample_rate: int = 16000,
        enable_vad: bool = True,
        auto_rotate: bool = True,
        max_session_duration: float = 20 * 60,
        save_audio: bool = True
    ):
        """
        初始化实时转录器

        Args:
            api_key: DashScope API Key
            sample_rate: 音频采样率
            enable_vad: 是否启用语音活动检测
            auto_rotate: 是否启用自动会话轮替（支持长时间录音）
            max_session_duration: 单个会话最大时长（秒），默认20分钟
            save_audio: 是否保存完整音频数据用于导出WAV文件，默认True
        """
        # 优先使用传入的api_key，然后使用settings中的配置
        from config.settings import settings
        self.api_key = api_key or settings.api.dashscope_api_key
        self.sample_rate = sample_rate
        self.enable_vad = enable_vad
        self.auto_rotate = auto_rotate
        self.max_session_duration = max_session_duration
        self.save_audio = save_audio

        # 音频录制器
        self.audio_config = AudioConfig(
            sample_rate=sample_rate,
            channels=1,
            chunk_size=1024,
            save_audio=save_audio
        )
        self.recorder = AudioRecorder(config=self.audio_config)

        # ASR 客户端
        self.asr_config = ASRConfig(
            api_key=self.api_key or "",
            sample_rate=sample_rate,
            enable_vad=enable_vad,
            auto_rotate=auto_rotate,
            max_session_duration=max_session_duration,
            rotate_on_silence=True
        )
        self.asr_client: Optional[DashScopeASRClient] = None
        
        # 状态管理
        self.state = TranscriberState()
        
        # 回调
        self.on_text_callback: Optional[Callable[[str, bool], None]] = None
        self.on_partial: Optional[Callable[[str], None]] = None
        self.on_final: Optional[Callable[[str], None]] = None
        self.on_status_change: Optional[Callable[[str], None]] = None
        
        # 结果收集
        self.full_transcription = ""
        self.partial_buffer = ""
        
        # 线程
        self._recognition_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        logger.info("RealtimeTranscriber 初始化完成")
    
    def start(
        self,
        on_text: Optional[Callable[[str, bool], None]] = None,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
        on_status_change: Optional[Callable[[str], None]] = None,
        device_index: Optional[int] = None
    ) -> bool:
        """
        开始实时转录
        
        Args:
            on_text: 文本回调(text: str, is_final: bool)
            on_partial: 中间结果回调
            on_final: 最终结果回调
            on_status_change: 状态变化回调
            device_index: 音频设备索引
            
        Returns:
            是否启动成功
        """
        if self.state.is_recording:
            logger.warning("转录已在进行中")
            return False
        
        try:
            # 保存回调
            self.on_text_callback = on_text
            self.on_partial = on_partial
            self.on_final = on_final
            self.on_status_change = on_status_change
            
            # 1. 连接 ASR 服务
            logger.info("[Transcriber] 正在连接 ASR 服务...")
            self._update_status("connecting")
            
            # 创建 ASR 客户端
            self.asr_client = DashScopeASRClient(self.asr_config)
            
            # 启动 ASR 服务
            started = self.asr_client.start(
                on_partial=self._on_asr_partial,
                on_final=self._on_asr_final,
                on_speech_start=self._on_speech_start,
                on_speech_stop=self._on_speech_stop,
                on_error=self._on_asr_error
            )
            
            if not started:
                logger.error("[Transcriber] ASR 服务启动失败")
                self._update_status("connection_failed")
                return False
            
            self.state.is_connected = True
            logger.info("[Transcriber] ASR 服务连接成功")
            
            # 2. 开始音频录制
            logger.info("[Transcriber] 开始音频录制...")
            self._update_status("starting_recording")
            
            def on_audio(data: bytes):
                """音频数据回调 - 实时发送给 ASR"""
                if self.asr_client and self.state.is_recording:
                    self.asr_client.send_audio(data)
            
            self.recorder.start(
                on_audio=on_audio,
                device_index=device_index
            )
            
            self.state.is_recording = True
            self.state.start_time = time.time()
            self._stop_event.clear()
            
            self._update_status("recording")
            logger.info("[Transcriber] 实时转录已启动")
            
            return True
            
        except Exception as e:
            logger.error(f"[Transcriber] 启动失败: {e}")
            self._update_status(f"error: {e}")
            self._cleanup()
            return False
    
    def stop(self) -> str:
        """
        停止实时转录
        
        Returns:
            完整转录文本
        """
        if not self.state.is_recording:
            logger.debug("[Transcriber] 转录未在进行中")
            return self.full_transcription
        
        logger.info("[Transcriber] 正在停止转录...")
        self._update_status("stopping")
        
        # 设置停止事件
        self._stop_event.set()
        
        # 停止音频录制
        try:
            self.recorder.stop()
            logger.debug("[Transcriber] 音频录制已停止")
        except Exception as e:
            logger.error(f"[Transcriber] 停止录音失败: {e}")
        
        # 结束 ASR 会话
        if self.asr_client:
            try:
                # 停止 ASR 服务并获取转录结果
                self.asr_client.stop()
                time.sleep(0.5)  # 等待最后结果
                self.full_transcription = self.asr_client.get_transcription()
                logger.debug("[Transcriber] ASR 会话已结束")
            except Exception as e:
                logger.error(f"[Transcriber] 结束 ASR 会话失败: {e}")
        
        # 关闭连接
        self._cleanup()
        
        # 计算统计
        if self.state.start_time:
            self.state.audio_duration = time.time() - self.state.start_time
        
        self.state.reset()
        self._update_status("stopped")
        
        logger.info(f"[Transcriber] 转录完成，时长: {self.state.audio_duration:.1f}秒")
        logger.info(f"[Transcriber] 完整文本: {self.full_transcription[:100]}...")
        
        return self.full_transcription
    
    def _on_asr_partial(self, text: str):
        """ASR 中间结果回调"""
        self.partial_buffer = text
        
        if self.on_partial:
            try:
                self.on_partial(text)
            except Exception as e:
                logger.error(f"[Transcriber] 中间结果回调出错: {e}")
        
        if self.on_text_callback:
            try:
                self.on_text_callback(text, False)
            except Exception as e:
                logger.error(f"[Transcriber] 文本回调出错: {e}")
    
    def _on_asr_final(self, text: str):
        """ASR 最终结果回调"""
        # 累加到完整转录
        if self.full_transcription:
            self.full_transcription += " " + text
        else:
            self.full_transcription = text
        
        # 清空中间结果
        self.partial_buffer = ""
        
        if self.on_final:
            try:
                self.on_final(text)
            except Exception as e:
                logger.error(f"[Transcriber] 最终结果回调出错: {e}")
        
        if self.on_text_callback:
            try:
                self.on_text_callback(text, True)
            except Exception as e:
                logger.error(f"[Transcriber] 文本回调出错: {e}")
    
    def _on_speech_start(self):
        """检测到开始说话"""
        logger.debug("[Transcriber] 检测到开始说话")
        self._update_status("speech_start")
    
    def _on_speech_stop(self):
        """检测到停止说话"""
        logger.debug("[Transcriber] 检测到停止说话")
        self._update_status("speech_stop")
    
    def _on_asr_error(self, error: Exception):
        """ASR 错误回调"""
        logger.error(f"[Transcriber] ASR 错误: {error}")
        self._update_status(f"asr_error: {error}")
    
    def _update_status(self, status: str):
        """更新状态"""
        logger.debug(f"[Transcriber] 状态: {status}")
        if self.on_status_change:
            try:
                self.on_status_change(status)
            except Exception as e:
                logger.error(f"[Transcriber] 状态回调出错: {e}")
    
    def _cleanup(self):
        """清理资源"""
        try:
            if self.asr_client:
                self.asr_client.stop()
                self.asr_client = None
        except Exception as e:
            logger.debug(f"[Transcriber] 清理 ASR 客户端时出错: {e}")

        try:
            self.recorder.stop()
        except Exception as e:
            logger.debug(f"[Transcriber] 清理音频录制器时出错: {e}")

        # 清空所有回调引用，避免循环引用
        self.on_text_callback = None
        self.on_partial = None
        self.on_final = None
        self.on_status_change = None

        # 清空累积文本
        self.full_transcription = ""
        self.partial_buffer = ""

        self.state.is_recording = False
        self.state.is_connected = False
    
    def get_transcription(self) -> str:
        """获取当前完整转录文本"""
        # 如果有 ASR 客户端，获取最新结果
        if self.asr_client:
            asr_text = self.asr_client.get_transcription()
            if asr_text:
                self.full_transcription = asr_text
        
        return self.full_transcription.strip()
    
    def get_current_partial(self) -> str:
        """获取当前中间结果"""
        return self.partial_buffer
    
    def is_recording(self) -> bool:
        """是否正在录制"""
        return self.state.is_recording
    
    def get_duration(self) -> float:
        """获取录制时长"""
        if self.state.start_time and self.state.is_recording:
            return time.time() - self.state.start_time
        return self.state.audio_duration

    def save_audio_wav(self, output_path: Path) -> None:
        """
        保存原始录音为 WAV 文件

        Args:
            output_path: 输出文件路径
        """
        self.recorder.save_wav(output_path)

    def get_audio_duration(self) -> float:
        """
        获取实际音频时长（从录制数据计算）

        Returns:
            音频时长（秒）
        """
        return self.recorder.get_duration()

    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.stop()


# 测试代码
if __name__ == "__main__":
    from utils.logger import init_logger
    
    init_logger(log_level="INFO")
    
    print("=" * 60)
    print("RealtimeTranscriber 测试")
    print("=" * 60)
    
    # 创建转录器
    transcriber = RealtimeTranscriber()
    
    print("\n初始化测试:")
    print(f"  采样率: {transcriber.sample_rate}Hz")
    print(f"  VAD: {'启用' if transcriber.enable_vad else '禁用'}")
    
    print("\n" + "=" * 60)
    print("基本功能测试完成！")
    print("=" * 60)
    
    # 注意：实际测试需要有效的 API Key
    print("\n提示: 要测试完整功能，需要:")
    print("  1. 配置有效的 DashScope API Key")
    print("  2. 运行 test_realtime_asr.py 完整测试")
