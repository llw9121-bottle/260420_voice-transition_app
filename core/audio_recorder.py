"""
音频录制模块

提供麦克风音频流的录制、设备管理和音频数据处理功能。
支持实时音频流输出，适配DashScope实时语音识别。
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import threading
from dataclasses import dataclass
from queue import Queue
from typing import Callable, List, Optional

import numpy as np
import pyaudio

from utils.exceptions import AudioDeviceException, AudioStreamException
from utils.logger import logger


@dataclass
class AudioDevice:
    """音频设备信息"""
    index: int
    name: str
    max_input_channels: int
    default_sample_rate: float


@dataclass
class AudioConfig:
    """音频配置参数"""
    sample_rate: int = 16000       # 采样率(Hz)
    channels: int = 1              # 声道数(单声道)
    chunk_size: int = 1024         # 音频块大小
    format: int = None             # 音频格式
    save_audio: bool = True        # 是否保存完整音频数据（用于保存WAV文件）

    def __post_init__(self):
        if self.format is None:
            self.format = pyaudio.paInt16  # 16bit PCM


class AudioRecorder:
    """
    音频录制器
    
    基于PyAudio的音频录制封装，支持：
    1. 麦克风设备检测和选择
    2. 实时音频流录制
    3. 音频数据队列输出
    4. 录制状态管理
    """
    
    def __init__(self, config: Optional[AudioConfig] = None):
        """
        初始化音频录制器
        
        Args:
            config: 音频配置参数，使用默认配置时可不传
        """
        self.config = config or AudioConfig()
        self.audio = pyaudio.PyAudio()
        self.stream: Optional[pyaudio.Stream] = None
        self.device_index: Optional[int] = None
        
        # 录制状态
        self.is_recording = False
        self.record_thread: Optional[threading.Thread] = None
        
        # 音频数据队列（用于实时输出）
        self.audio_queue: Queue = Queue()

        # 回调函数
        self.on_audio_callback: Optional[Callable[[bytes], None]] = None

        # 存储完整音频数据（用于保存到文件）
        self.recorded_frames: List[bytes] = []

        # 音量电平计算（用于可视化）
        self._current_rms: float = 0.0
        self._max_rms: float = 0.0

        logger.info("音频录制器初始化完成")
    
    def list_devices(self) -> List[AudioDevice]:
        """
        列出所有可用的音频输入设备
        
        Returns:
            音频设备列表
        """
        devices = []
        try:
            for i in range(self.audio.get_device_count()):
                info = self.audio.get_device_info_by_index(i)
                
                # 只收集输入设备（maxInputChannels > 0）
                if info.get("maxInputChannels", 0) > 0:
                    device = AudioDevice(
                        index=i,
                        name=info.get("name", f"设备{i}"),
                        max_input_channels=info.get("maxInputChannels", 0),
                        default_sample_rate=info.get("defaultSampleRate", 44100.0)
                    )
                    devices.append(device)
                    
            logger.debug(f"发现 {len(devices)} 个音频输入设备")
            return devices
            
        except Exception as e:
            logger.error(f"列举音频设备失败: {e}")
            raise AudioDeviceException(f"无法获取设备列表: {e}")
    
    def get_default_device(self) -> AudioDevice:
        """
        获取默认音频输入设备
        
        Returns:
            默认音频设备
            
        Raises:
            AudioDeviceException: 无法获取默认设备
        """
        try:
            default_index = self.audio.get_default_input_device_info().get("index")
            info = self.audio.get_device_info_by_index(default_index)
            
            return AudioDevice(
                index=default_index,
                name=info.get("name", "默认设备"),
                max_input_channels=info.get("maxInputChannels", 0),
                default_sample_rate=info.get("defaultSampleRate", 44100.0)
            )
            
        except Exception as e:
            logger.error(f"获取默认音频设备失败: {e}")
            raise AudioDeviceException(f"无法获取默认设备: {e}")
    
    def select_device(self, device_index: int) -> None:
        """
        选择音频输入设备
        
        Args:
            device_index: 设备索引号
            
        Raises:
            AudioDeviceException: 设备不可用
        """
        try:
            info = self.audio.get_device_info_by_index(device_index)
            
            if info.get("maxInputChannels", 0) <= 0:
                raise AudioDeviceException(
                    f"设备 {device_index} 不支持音频输入",
                    device_index=device_index
                )
            
            self.device_index = device_index
            logger.info(f"已选择音频设备: {info.get('name')} (索引: {device_index})")
            
        except Exception as e:
            logger.error(f"选择音频设备 {device_index} 失败: {e}")
            raise AudioDeviceException(f"设备选择失败: {e}", device_index=device_index)
    
    def start(
        self,
        on_audio: Optional[Callable[[bytes], None]] = None,
        device_index: Optional[int] = None
    ) -> None:
        """
        开始录制音频
        
        Args:
            on_audio: 音频数据回调函数，每录制一块音频调用一次
            device_index: 指定设备索引，不传则使用默认设备
            
        Raises:
            AudioDeviceException: 设备初始化失败
            AudioStreamException: 音频流启动失败
        """
        if self.is_recording:
            logger.warning("录音已在进行中，忽略重复启动请求")
            return
        
        try:
            # 设置回调
            self.on_audio_callback = on_audio
            
            # 选择设备
            if device_index is not None:
                self.select_device(device_index)
            elif self.device_index is None:
                default = self.get_default_device()
                self.device_index = default.index
                logger.info(f"使用默认设备: {default.name}")
            
            # 打开音频流
            self.stream = self.audio.open(
                format=self.config.format,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=self.config.chunk_size,
                stream_callback=self._stream_callback
            )
            
            self.is_recording = True
            # 清空之前的录制数据
            self.recorded_frames.clear()
            # 重置音量电平统计
            self.reset_volume_level()
            logger.info(
                f"开始录音: {self.config.sample_rate}Hz, "
                f"{self.config.channels}通道, 设备索引: {self.device_index}"
            )
            
        except Exception as e:
            logger.error(f"启动录音失败: {e}")
            self._cleanup()
            raise AudioStreamException(f"无法启动录音: {e}")
    
    def _stream_callback(
        self,
        in_data: bytes,
        frame_count: int,
        time_info: dict,
        status: int
    ) -> tuple:
        """
        PyAudio流回调函数

        每当有新的音频数据块可用时被调用。
        """
        if in_data and self.is_recording:
            # 放入队列
            self.audio_queue.put(in_data)

            # 累积音频数据（用于保存到文件），仅在启用保存时
            if self.config.save_audio:
                self.recorded_frames.append(in_data)

            # 计算当前音量电平（用于可视化）
            self._update_volume_level(in_data)

            # 调用用户回调
            if self.on_audio_callback:
                try:
                    self.on_audio_callback(in_data)
                except Exception as e:
                    logger.error(f"音频回调函数执行失败: {e}")

        # 返回继续录制
        return (in_data, pyaudio.paContinue)
    
    def stop(self) -> None:
        """
        停止录制音频
        
        停止音频流并释放资源。
        """
        if not self.is_recording:
            logger.debug("录音未在进行中，无需停止")
            return
        
        logger.info("停止录音")
        self.is_recording = False
        self._cleanup()
    
    def _cleanup(self) -> None:
        """清理资源"""
        # 停止并关闭流
        if self.stream:
            try:
                if self.stream.is_active():
                    self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                logger.debug(f"关闭音频流时出错: {e}")
            finally:
                self.stream = None

        # 清空音频数据，释放内存
        self.recorded_frames.clear()
        # 清空队列
        self.clear_audio_queue()

        logger.debug("音频资源已清理")
    
    def get_audio_data(self, timeout: float = 0.1) -> Optional[bytes]:
        """
        从队列获取音频数据（非阻塞）

        Args:
            timeout: 等待超时时间（秒）

        Returns:
            音频数据字节，超时返回None
        """
        try:
            return self.audio_queue.get(timeout=timeout)
        except Exception as e:
            logger.debug(f"获取音频数据超时: {e}")
            return None
    
    def get_audio_queue_size(self) -> int:
        """
        获取音频队列中的数据块数量
        
        Returns:
            队列大小
        """
        return self.audio_queue.qsize()
    
    def clear_audio_queue(self) -> None:
        """清空音频队列"""
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except Exception as e:
                logger.debug(f"清空音频队列时出错: {e}")
                break
        logger.debug("音频队列已清空")
    
    def convert_to_numpy(self, audio_bytes: bytes) -> np.ndarray:
        """
        将字节音频数据转换为numpy数组

        Args:
            audio_bytes: PCM音频字节数据

        Returns:
            numpy数组
        """
        dtype = np.int16  # 16bit PCM
        return np.frombuffer(audio_bytes, dtype=dtype)

    def get_recorded_data(self) -> bytes:
        """
        获取录制的完整音频数据

        Returns:
            所有录制帧拼接后的完整字节数据
        """
        if not self.recorded_frames:
            return b""
        return b"".join(self.recorded_frames)

    def get_total_bytes(self) -> int:
        """
        获取录制的总字节数

        Returns:
            总字节数
        """
        return sum(len(frame) for frame in self.recorded_frames)

    def get_duration(self) -> float:
        """
        估算录制时长

        Returns:
            估算时长（秒）
        """
        # 16bit = 2 bytes per sample
        bytes_per_second = self.config.sample_rate * self.config.channels * 2
        total_bytes = self.get_total_bytes()
        return total_bytes / bytes_per_second if bytes_per_second > 0 else 0.0

    def save_wav(self, output_path: Path) -> None:
        """
        将录制的音频保存为 WAV 文件

        Args:
            output_path: 输出文件路径
        """
        import wave

        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 获取完整音频数据
        audio_data = self.get_recorded_data()

        # 创建 WAV 文件
        with wave.open(str(output_path), 'wb') as wf:
            wf.setnchannels(self.config.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.config.format))
            wf.setframerate(self.config.sample_rate)
            wf.writeframes(audio_data)

        logger.info(f"原始录音已保存: {output_path} ({len(audio_data)} bytes)")

    def _update_volume_level(self, audio_bytes: bytes) -> None:
        """
        更新当前音量电平（RMS计算）

        Args:
            audio_bytes: 音频数据字节（16bit PCM）
        """
        try:
            # 转换为numpy数组
            samples = self.convert_to_numpy(audio_bytes)
            # 计算RMS（均方根）
            if len(samples) > 0:
                rms = np.sqrt(np.mean(np.square(samples.astype(np.float32))))
                # 使用指数移动平均平滑变化
                self._current_rms = 0.6 * self._current_rms + 0.4 * rms
                # 更新最大值
                if self._current_rms > self._max_rms:
                    self._max_rms = self._current_rms
        except Exception as e:
            logger.debug(f"音量电平计算失败: {e}")

    def get_current_volume(self) -> float:
        """
        获取当前音量电平，归一化到 0.0-1.0 范围

        Returns:
            归一化音量，0 表示静音，1 表示最大音量
        """
        if self._max_rms <= 0:
            return 0.0
        # 归一化，并使用对数缩放让人眼感受更自然
        normalized = min(1.0, self._current_rms / max(self._max_rms, 32768))
        # 对数缩放，增强低音量可见性
        if normalized > 0:
            return np.log10(1 + 9 * normalized)
        return 0.0

    def reset_volume_level(self) -> None:
        """重置音量电平统计（每次录音开始时调用）"""
        self._current_rms = 0.0
        self._max_rms = 0.0

    def __del__(self):
        """析构时清理资源"""
        self._cleanup()
        if hasattr(self, 'audio') and self.audio:
            try:
                self.audio.terminate()
            except Exception as e:
                logger.debug(f"终止音频系统时出错: {e}")


# 便捷函数
def get_audio_devices() -> List[AudioDevice]:
    """获取所有可用音频输入设备（便捷函数）"""
    audio = pyaudio.PyAudio()
    try:
        devices = []
        for i in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                devices.append(AudioDevice(
                    index=i,
                    name=info.get("name", f"设备{i}"),
                    max_input_channels=info.get("maxInputChannels", 0),
                    default_sample_rate=info.get("defaultSampleRate", 44100.0)
                ))
        return devices
    finally:
        audio.terminate()


# 测试代码
if __name__ == "__main__":
    from utils.logger import init_logger
    
    init_logger(log_level="DEBUG")
    
    print("=== 音频设备测试 ===")
    devices = get_audio_devices()
    print(f"\n发现 {len(devices)} 个输入设备:")
    for device in devices:
        print(f"  [{device.index}] {device.name}")
        print(f"      最大通道: {device.max_input_channels}, 默认采样率: {device.default_sample_rate}Hz")
    
    if not devices:
        print("未找到音频输入设备，无法继续测试")
        exit(1)
    
    print("\n=== 录音测试 ===")
    print("准备录制5秒音频...")
    
    recorder = AudioRecorder()
    recorded_frames = []
    
    def on_audio(data):
        recorded_frames.append(data)
        if len(recorded_frames) % 10 == 0:
            print(f"已录制 {len(recorded_frames)} 块音频数据")
    
    recorder.start(on_audio=on_audio)
    
    # 录制5秒
    import time
    time.sleep(5)
    
    recorder.stop()
    
    total_bytes = sum(len(f) for f in recorded_frames)
    print(f"\n录制完成!")
    print(f"  音频块数量: {len(recorded_frames)}")
    print(f"  总字节数: {total_bytes} bytes")
    print(f"  音频时长: 约{len(recorded_frames) * 1024 / 16000:.1f}秒")
    
    print("\n测试通过!")
