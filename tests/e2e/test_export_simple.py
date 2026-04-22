"""
导出功能简单测试 - 不需要GUI

测试导出器的核心功能。
"""

import sys
from pathlib import Path

# 设置项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.formatter.base import FormattedDocument, FormattingStyle
from core.formatter.exporters import JSONExporter, MarkdownExporter
from core.formatter.naming import NamingStrategy


def test_naming_strategy():
    """测试命名策略"""
    print("测试命名策略...")
    
    # 测试各种模板
    templates = ["timestamp", "timestamp_title", "date_title"]
    
    for template in templates:
        try:
            strategy = NamingStrategy(template=template)
            filename = strategy.generate(
                title="测试会议记录",
                session_id="test_123"
            )
            print(f"  模板 '{template}' -> {filename}")
        except Exception as e:
            print(f"  模板 '{template}' 失败: {e}")
    
    print()


def test_exporters():
    """测试导出器"""
    print("测试导出器...")
    
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
    
    # 测试JSON导出
    print("  测试 JSON 导出器...")
    try:
        exporter = JSONExporter()
        output_path = output_dir / "test_export.json"
        result_path = exporter.export(doc, output_path)
        
        # 验证文件
        assert result_path.exists(), "文件未创建"
        content = result_path.read_text(encoding='utf-8')
        assert "测试文档" in content, "内容不正确"
        
        print(f"    成功: {result_path}")
    except Exception as e:
        print(f"    失败: {e}")
    
    # 测试Markdown导出
    print("  测试 Markdown 导出器...")
    try:
        exporter = MarkdownExporter()
        output_path = output_dir / "test_export.md"
        result_path = exporter.export(doc, output_path)
        
        # 验证文件
        assert result_path.exists(), "文件未创建"
        content = result_path.read_text(encoding='utf-8')
        assert "# 测试文档" in content, "标题不正确"
        
        print(f"    成功: {result_path}")
    except Exception as e:
        print(f"    失败: {e}")
    
    print()


def main():
    """主函数"""
    print("=" * 60)
    print("导出功能单元测试")
    print("=" * 60)
    print()
    
    test_naming_strategy()
    test_exporters()
    
    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
