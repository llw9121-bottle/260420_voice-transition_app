"""
音频设备检测单元测试

测试音频设备信息解析，不需要实际音频硬件即可运行。
"""

import pytest
from unittest.mock import Mock, patch

# 添加项目根目录到Python路径
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.audio_recorder import AudioDevice, AudioConfig, AudioRecorder


class TestAudioDevice:
    """音频设备信息类测试"""

    def test_audio_device_creation(self):
        """测试创建音频设备信息"""
        device = AudioDevice(
            index=0,
            name="Test Microphone",
            max_input_channels=1,
            default_sample_rate=44100.0
        )
        assert device.index == 0
        assert device.name == "Test Microphone"
        assert device.max_input_channels == 1
        assert device.default_sample_rate == 44100.0

    def test_audio_device_default_values(self):
        """测试音频设备默认值处理"""
        device = AudioDevice(
            index=1,
            name="",
            max_input_channels=2,
            default_sample_rate=0.0
        )
        assert device.name == ""
        assert device.default_sample_rate == 0.0


class TestAudioConfig:
    """音频配置类测试"""

    def test_audio_config_default(self):
        """测试默认音频配置"""
        config = AudioConfig()
        assert config.sample_rate == 16000
        assert config.channels == 1
        assert config.chunk_size == 1024
        assert config.save_audio is True  # 默认保存音频

    def test_audio_config_custom(self):
        """测试自定义音频配置"""
        config = AudioConfig(
            sample_rate=44100,
            channels=2,
            chunk_size=2048,
            save_audio=False
        )
        assert config.sample_rate == 44100
        assert config.channels == 2
        assert config.chunk_size == 2048
        assert config.save_audio is False

    def test_audio_config_post_init(self):
        """测试__post_init__设置默认format"""
        config = AudioConfig()
        # 默认应该设置为 pyaudio.paInt16
        import pyaudio
        assert config.format == pyaudio.paInt16


class TestAudioRecorderMock:
    """使用mock的AudioRecorder测试"""

    @patch('pyaudio.PyAudio')
    def test_audio_recorder_init(self, mock_pyaudio_class):
        """测试音频录制器初始化"""
        mock_pyaudio = Mock()
        mock_pyaudio_class.return_value = mock_pyaudio

        recorder = AudioRecorder()
        assert recorder.config is not None
        assert recorder.audio is not None
        assert recorder.stream is None
        assert not recorder.is_recording
        assert len(recorder.recorded_frames) == 0

    @patch('pyaudio.PyAudio')
    def test_clear_audio_queue(self, mock_pyaudio_class):
        """测试清空音频队列"""
        mock_pyaudio = Mock()
        mock_pyaudio_class.return_value = mock_pyaudio

        recorder = AudioRecorder()
        # 清空空队列应该不会出错
        recorder.clear_audio_queue()
        assert recorder.audio_queue.qsize() == 0

    @patch('pyaudio.PyAudio')
    def test_get_duration_empty(self, mock_pyaudio_class):
        """测试空录制时长计算"""
        mock_pyaudio = Mock()
        mock_pyaudio_class.return_value = mock_pyaudio

        recorder = AudioRecorder()
        assert recorder.get_duration() == 0.0

    @patch('pyaudio.PyAudio')
    def test_get_total_bytes_empty(self, mock_pyaudio_class):
        """测试空录制字节数"""
        mock_pyaudio = Mock()
        mock_pyaudio_class.return_value = mock_pyaudio

        recorder = AudioRecorder()
        assert recorder.get_total_bytes() == 0

    @patch('pyaudio.PyAudio')
    def test_get_recorded_data_empty(self, mock_pyaudio_class):
        """测试空录制数据获取"""
        mock_pyaudio = Mock()
        mock_pyaudio_class.return_value = mock_pyaudio

        recorder = AudioRecorder()
        assert recorder.get_recorded_data() == b""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
