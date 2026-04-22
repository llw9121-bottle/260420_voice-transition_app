"""
实时语音识别测试脚本

测试功能：
- 从麦克风实时录音
- 通过 DashScope WebSocket 进行实时转录
- 显示中间结果（实时）和最终结果

使用方法：
1. 确保已配置 DashScope API Key（在 .env 文件中）
2. 运行脚本：python test_realtime_asr.py
3. 对着麦克风说话，观察实时转录结果
4. 按 Ctrl+C 停止录制

注意：
- 首次运行可能需要安装依赖：pip install -r requirements.txt
- 确保麦克风权限已开启
"""

import sys
import time
import threading
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.logger import init_logger
from core.realtime_transcriber import RealtimeTranscriber
from config.settings import settings


def print_header():
    """打印标题"""
    print("=" * 70)
    print("        DashScope 实时语音识别测试")
    print("=" * 70)
    print("\n功能说明：")
    print("  - 实时录音并转录为文字")
    print("  - 支持中文语音识别")
    print("  - 显示中间结果和最终结果")
    print("\n操作说明：")
    print("  1. 对着麦克风说话")
    print("  2. 观察下方输出的转录结果")
    print("  3. 按 Ctrl+C 停止录制")
    print("\n" + "=" * 70)
    print()


def print_result(text: str, is_final: bool = False, partial: str = ""):
    """打印识别结果"""
    if is_final:
        # 最终结果 - 绿色
        print(f"\n  [最终结果] {text}")
        print(f"  {'─' * 60}\n")
    elif partial:
        # 中间结果 - 在同一行更新
        print(f"\r  [识别中...] {partial:<50}", end="", flush=True)


def main():
    """主函数"""
    # 初始化日志
    init_logger(log_level="INFO")
    
    # 打印标题
    print_header()
    
    # 检查 API Key
    api_key = settings.api.dashscope_api_key
    if not api_key or api_key == "your_dashscope_api_key_here":
        print("❌ 错误：未配置 DashScope API Key")
        print("\n请在 .env 文件中设置：")
        print("  DASHSCOPE_API_KEY=your_actual_api_key")
        print("\n获取 API Key: https://help.aliyun.com/zh/dashscope/")
        return 1
    
    # 创建转录器
    print("🎙️  正在初始化实时转录器...")
    try:
        transcriber = RealtimeTranscriber(
            api_key=api_key,
            sample_rate=16000,
            enable_vad=True
        )
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return 1
    
    print("✅ 初始化完成！\n")
    print("🎤 请开始说话...\n")
    
    # 定义回调
    def on_text(text: str, is_final: bool):
        """文本回调"""
        if is_final:
            print_result(text, is_final=True)
        else:
            print_result("", is_final=False, partial=text)
    
    def on_partial(text: str):
        """中间结果回调"""
        print(f"\r  [识别中...] {text:<50}", end="", flush=True)
    
    def on_final(text: str):
        """最终结果回调"""
        print(f"\n  [最终结果] {text}")
        print(f"  {'─' * 60}\n")
    
    def on_status(status: str):
        """状态回调"""
        status_map = {
            "connecting": "🔗 正在连接...",
            "connection_failed": "❌ 连接失败",
            "starting_recording": "🎙️  开始录音...",
            "recording": "🎤 正在录制...",
            "speech_start": "🗣️  检测到说话...",
            "speech_stop": "✋ 说话结束",
            "stopping": "🛑 正在停止...",
            "stopped": "✅ 已停止"
        }
        if status in status_map:
            print(f"  {status_map[status]}")
    
    # 开始转录
    try:
        success = transcriber.start(
            on_text=on_text,
            on_partial=on_partial,
            on_final=on_final,
            on_status_change=on_status
        )
        
        if not success:
            print("❌ 启动失败")
            return 1
        
        # 保持运行直到用户中断
        print("\n" + "─" * 70)
        print("按 Ctrl+C 停止录制")
        print("─" * 70 + "\n")
        
        try:
            while transcriber.is_recording():
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n\n🛑 收到中断信号，正在停止...")
        
        # 停止转录
        print("\n正在停止...")
        final_text = transcriber.stop()
        
        # 打印最终结果
        print("\n" + "=" * 70)
        print("                     转录结果")
        print("=" * 70)
        print(f"\n{final_text}\n")
        print("=" * 70)
        
        # 打印统计
        duration = transcriber.get_duration()
        print(f"\n📊 统计信息:")
        print(f"  录制时长: {duration:.1f} 秒")
        print(f"  转录字数: {len(final_text)} 字")
        if duration > 0:
            print(f"  语速: {len(final_text) / duration:.1f} 字/秒")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
