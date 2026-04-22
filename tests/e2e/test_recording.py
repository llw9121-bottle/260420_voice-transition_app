"""
音频录制流程测试

测试完整的录音流程：
1. 设备检测
2. 开始录音
3. 录制5秒
4. 保存WAV文件
5. 停止录音
"""

import io
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

# 设置标准输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.audio_recorder import AudioRecorder, get_audio_devices
from utils.logger import init_logger

# 配置参数
RECORD_SECONDS = 5  # 录音时长
OUTPUT_DIR = Path("./output/audio")


def test_recording_flow():
    """测试完整录音流程"""
    
    print("=" * 60)
    print("音频录制流程测试")
    print("=" * 60)
    
    # 1. 设备检测
    print("\n【步骤1】检测音频设备...")
    devices = get_audio_devices()
    print(f"发现 {len(devices)} 个音频输入设备:")
    for device in devices:
        print(f"  [{device.index}] {device.name}")
        print(f"      最大通道: {device.max_input_channels}, "
              f"默认采样率: {device.default_sample_rate}Hz")
    
    if not devices:
        print("错误: 未找到音频输入设备，无法继续测试")
        return False
    
    # 2. 初始化录音器
    print("\n【步骤2】初始化录音器...")
    recorder = AudioRecorder()
    print("录音器初始化完成")
    print(f"  采样率: {recorder.config.sample_rate}Hz")
    print(f"  声道数: {recorder.config.channels}")
    print(f"  音频块大小: {recorder.config.chunk_size}")
    
    # 3. 准备输出目录
    print("\n【步骤3】准备输出目录...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"test_recording_{timestamp}.wav"
    print(f"  输出文件: {output_file}")
    
    # 4. 开始录音
    print("\n【步骤4】开始录音...")
    recorded_frames = []
    
    def on_audio(data):
        """音频数据回调"""
        recorded_frames.append(data)
        # 每10块打印一次进度
        if len(recorded_frames) % 10 == 0:
            elapsed = len(recorded_frames) * 1024 / 16000
            print(f"  已录制: {elapsed:.1f}秒, "
                  f"数据块: {len(recorded_frames)}")
    
    # 开始录音
    recorder.start(on_audio=on_audio)
    print(f"  录音进行中，请对着麦克风说话...")
    
    # 录制指定时长
    print(f"  将录制 {RECORD_SECONDS} 秒...")
    time.sleep(RECORD_SECONDS)
    
    # 5. 停止录音
    print("\n【步骤5】停止录音...")
    recorder.stop()
    print("  录音已停止")
    
    # 6. 保存WAV文件
    print("\n【步骤6】保存音频文件...")
    
    if not recorded_frames:
        print("  错误: 没有录制到任何数据")
        return False
    
    # 合并所有音频数据
    audio_data = b''.join(recorded_frames)
    
    # 写入WAV文件
    with wave.open(str(output_file), 'wb') as wf:
        wf.setnchannels(recorder.config.channels)
        wf.setsampwidth(2)  # 16-bit = 2 bytes
        wf.setframerate(recorder.config.sample_rate)
        wf.writeframes(audio_data)
    
    # 计算音频信息
    duration = len(audio_data) / (recorder.config.sample_rate * recorder.config.channels * 2)
    file_size = output_file.stat().st_size
    
    print(f"  文件已保存: {output_file}")
    print(f"  文件大小: {file_size / 1024:.1f} KB")
    print(f"  音频时长: {duration:.2f} 秒")
    print(f"  采样率: {recorder.config.sample_rate} Hz")
    print(f"  声道数: {recorder.config.channels}")
    
    print("\n" + "=" * 60)
    print("音频录制流程测试完成！")
    print("=" * 60)
    
    return True


def main():
    """主函数"""
    # 初始化日志
    init_logger(log_level="INFO")
    
    try:
        success = test_recording_flow()
        if success:
            print("\n✅ 测试通过！")
            sys.exit(0)
        else:
            print("\n❌ 测试失败！")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n用户中断测试")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
