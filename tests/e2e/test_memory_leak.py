"""
内存泄漏测试脚本

多次创建启动停止转录器，观察内存使用变化，判断是否存在内存泄漏。
不需要实际录音和API Key即可运行基础测试。
"""

import gc
import os
import time
import psutil
from typing import Callable


def get_memory_usage() -> float:
    """获取当前进程内存占用 (MB)"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # 转换为 MB


def print_memory_diff(label: str, before: float, after: float) -> None:
    """打印内存变化"""
    diff = after - before
    print(f"  {label}: 之前 {before:.2f} MB → 之后 {after:.2f} MB [变化: {diff:+.2f} MB]")


def test_multiple_start_stop(iterations: int = 10, delay: float = 0.5) -> None:
    """
    测试多次启动停止转录器，观察内存变化

    Args:
        iterations: 循环次数
        delay: 每次循环延迟（秒）
    """
    from core.realtime_transcriber import RealtimeTranscriber

    print(f"\n{'='*60}")
    print(f"测试: 多次创建/销毁 RealtimeTranscriber (迭代 {iterations} 次)")
    print(f"{'='*60}")

    # 初始内存
    gc.collect()
    initial_memory = get_memory_usage()
    print(f"初始内存: {initial_memory:.2f} MB\n")

    prev_memory = initial_memory
    memory_readings = [initial_memory]

    for i in range(iterations):
        before = get_memory_usage()

        # 创建转录器（不会实际启动音频和ASR）
        transcriber = RealtimeTranscriber()

        # 如果要测试完整路径可以启动后再停止
        # 这里只测试对象创建销毁
        transcriber.stop()

        # 删除引用
        del transcriber

        # 强制垃圾回收
        gc.collect()

        after = get_memory_usage()
        memory_readings.append(after)

        print_memory_diff(f"第 {i+1:2d} 次循环", before, after)

        prev_memory = after
        time.sleep(delay)

    # 最终结果
    gc.collect()
    final_memory = get_memory_usage()
    total_diff = final_memory - initial_memory

    print(f"\n{'='*60}")
    print(f"测试完成")
    print(f"初始内存: {initial_memory:.2f} MB")
    print(f"最终内存: {final_memory:.2f} MB")
    print(f"总变化: {total_diff:+.2f} MB")
    print()

    if total_diff < 10:
        print("✅ 结论: 内存增长在正常范围内，未发现明显内存泄漏")
    elif total_diff < 50:
        print("⚠️ 结论: 有一定内存增长，可能存在轻微泄漏，建议增加迭代次数再测试")
    else:
        print("❌ 结论: 内存增长明显，存在内存泄漏问题")
    print(f"{'='*60}")


def test_audio_recorder_only(iterations: int = 10) -> None:
    """单独测试 AudioRecorder 的内存泄漏"""
    from core.audio_recorder import AudioRecorder, AudioConfig

    print(f"\n{'='*60}")
    print(f"测试: 多次创建/销毁 AudioRecorder (迭代 {iterations} 次)")
    print(f"{'='*60}")

    gc.collect()
    initial_memory = get_memory_usage()
    print(f"初始内存: {initial_memory:.2f} MB\n")

    for i in range(iterations):
        before = get_memory_usage()

        # 使用 mock 不需要实际音频设备
        recorder = AudioRecorder()
        recorder.stop()
        del recorder

        gc.collect()

        after = get_memory_usage()
        print_memory_diff(f"第 {i+1:2d} 次循环", before, after)

    gc.collect()
    final_memory = get_memory_usage()
    total_diff = final_memory - initial_memory

    print(f"\n{'='*60}")
    print(f"测试完成")
    print(f"初始内存: {initial_memory:.2f} MB")
    print(f"最终内存: {final_memory:.2f} MB")
    print(f"总变化: {total_diff:+.2f} MB")
    print()

    if total_diff < 5:
        print("✅ 结论: AudioRecorder 内存清理正常")
    else:
        print("❌ 结论: AudioRecorder 可能存在内存泄漏")
    print(f"{'='*60}")


def test_audio_recorder_no_save(iterations: int = 10) -> None:
    """测试 save_audio=False 时的内存使用"""
    from core.audio_recorder import AudioRecorder, AudioConfig

    print(f"\n{'='*60}")
    print(f"测试: AudioRecorder with save_audio=False (迭代 {iterations} 次)")
    print(f"{'='*60}")

    gc.collect()
    initial_memory = get_memory_usage()
    print(f"初始内存: {initial_memory:.2f} MB\n")

    for i in range(iterations):
        before = get_memory_usage()

        config = AudioConfig(save_audio=False)
        recorder = AudioRecorder(config)
        recorder.stop()
        del recorder

        gc.collect()

        after = get_memory_usage()
        print_memory_diff(f"第 {i+1:2d} 次循环", before, after)

    gc.collect()
    final_memory = get_memory_usage()
    total_diff = final_memory - initial_memory

    print(f"\n{'='*60}")
    print(f"测试完成")
    print(f"初始内存: {initial_memory:.2f} MB")
    print(f"最终内存: {final_memory:.2f} MB")
    print(f"总变化: {total_diff:+.2f} MB")
    print()

    if total_diff < 5:
        print("✅ 结论: save_audio=False 模式内存清理正常（不累积帧数据）")
    else:
        print("❌ 结论: save_audio=False 模式仍有内存泄漏")
    print(f"{'='*60}")


def continuous_growth_test(iterations: int = 50) -> None:
    """长时间测试，看是否持续增长"""
    from core.realtime_transcriber import RealtimeTranscriber

    print(f"\n{'='*60}")
    print(f"长时间测试: {iterations} 次迭代，检测持续内存增长")
    print(f"{'='*60}")

    gc.collect()
    memory_history = []
    initial_memory = get_memory_usage()
    memory_history.append(initial_memory)

    print(f"初始内存: {initial_memory:.2f} MB")
    print("进度: ", end="", flush=True)

    for i in range(iterations):
        transcriber = RealtimeTranscriber()
        transcriber.stop()
        del transcriber

        if (i + 1) % 10 == 0:
            gc.collect()
            current = get_memory_usage()
            memory_history.append(current)
            print(f"{i+1} ", end="", flush=True)

    print("\n")

    gc.collect()
    final_memory = get_memory_usage()
    total_diff = final_memory - initial_memory

    print(f"最终内存: {final_memory:.2f} MB")
    print(f"总变化: {total_diff:+.2f} MB")
    print()

    print("历史记录 (每 10 次迭代):")
    for idx, mem in enumerate(memory_history):
        print(f"  第 {idx*10:3d} 次: {mem:.2f} MB")

    print(f"\n{'='*60}")


if __name__ == "__main__":
    print("内存泄漏测试 - 语音转录系统")
    print("=" * 60)

    try:
        import psutil
    except ImportError:
        print("❌ psutil 未安装，请先运行: pip install psutil")
        exit(1)

    # 运行所有测试
    test_multiple_start_stop(iterations=20, delay=0.2)
    test_audio_recorder_only(iterations=20)
    test_audio_recorder_no_save(iterations=20)

    # 如果前面测试正常，可以运行更长时间测试
    # continuous_growth_test(iterations=100)
