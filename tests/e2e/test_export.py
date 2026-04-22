"""
导出功能集成测试

测试导出对话框和导出器的完整集成。
"""

import sys
import threading
import time
from pathlib import Path

# 设置项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import customtkinter as ctk
from core.formatter.base import FormattedDocument, FormattingStyle


def test_export_dialog():
    """测试导出对话框"""
    print("开始测试导出对话框...")
    
    # 创建测试文档
    doc = FormattedDocument(
        title="测试文档",
        raw_text="这是原始文本内容。",
        formatted_text="这是格式化后的内容。",
        style=FormattingStyle.CLEANED,
        session_id="test_123",
        word_count=100,
        duration_seconds=60.0
    )
    
    # 创建主窗口
    root = ctk.CTk()
    root.title("导出功能测试")
    root.geometry("400x200")
    
    result = {"success": False, "error": None}
    
    def open_export_dialog():
        """打开导出对话框"""
        try:
            from gui.export_dialog import ExportDialog
            
            def on_export(file_path):
                print(f"导出成功: {file_path}")
                result["success"] = True
                status_label.configure(text=f"导出成功: {file_path.name}")
            
            dialog = ExportDialog(root, doc, on_export=on_export)
            print("导出对话框已打开")
        except Exception as e:
            print(f"打开导出对话框失败: {e}")
            result["error"] = str(e)
            status_label.configure(text=f"错误: {e}")
    
    # 状态标签
    status_label = ctk.CTkLabel(root, text="准备就绪")
    status_label.pack(pady=10)
    
    # 测试按钮
    test_button = ctk.CTkButton(
        root, 
        text="测试导出对话框", 
        command=open_export_dialog
    )
    test_button.pack(pady=10)
    
    # 自动打开对话框进行测试（在另一个线程中延迟执行）
    def delayed_open():
        time.sleep(1)
        root.after(0, open_export_dialog)
    
    threading.Thread(target=delayed_open, daemon=True).start()
    
    root.mainloop()
    
    return result


def test_exporters():
    """测试导出器"""
    print("\n测试导出器...")
    
    from core.formatter.exporters import JSONExporter, MarkdownExporter
    
    # 创建测试文档
    doc = FormattedDocument(
        title="测试文档",
        raw_text="这是原始文本内容。",
        formatted_text="这是格式化后的内容。",
        style=FormattingStyle.CLEANED,
        session_id="test_123",
        word_count=100,
        duration_seconds=60.0
    )
    
    # 创建输出目录
    output_dir = Path("./test_output")
    output_dir.mkdir(exist_ok=True)
    
    results = []
    
    # 测试JSON导出
    try:
        exporter = JSONExporter()
        output_path = output_dir / "test_export.json"
        result_path = exporter.export(doc, output_path)
        print(f"  JSON导出成功: {result_path}")
        results.append(("JSON", True, str(result_path)))
    except Exception as e:
        print(f"  JSON导出失败: {e}")
        results.append(("JSON", False, str(e)))
    
    # 测试Markdown导出
    try:
        exporter = MarkdownExporter()
        output_path = output_dir / "test_export.md"
        result_path = exporter.export(doc, output_path)
        print(f"  Markdown导出成功: {result_path}")
        results.append(("Markdown", True, str(result_path)))
    except Exception as e:
        print(f"  Markdown导出失败: {e}")
        results.append(("Markdown", False, str(e)))
    
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("导出功能集成测试")
    print("=" * 60)
    
    # 先测试导出器（无需GUI）
    exporter_results = test_exporters()
    
    print("\n" + "=" * 60)
    print("导出器测试结果:")
    for name, success, info in exporter_results:
        status = "通过" if success else "失败"
        print(f"  {name}: {status} - {info}")
    
    # 测试导出对话框（需要GUI）
    print("\n" + "=" * 60)
    print("测试导出对话框...")
    print("提示: 测试窗口将在1秒后自动打开导出对话框")
    print("=" * 60 + "\n")
    
    dialog_result = test_export_dialog()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
