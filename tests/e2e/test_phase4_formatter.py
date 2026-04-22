"""
Phase 4 格式化模块完整测试脚本

测试内容：
1. 文本清洗功能
2. 4种格式化风格
3. 关键行为匹配
4. 多格式导出（Word/Markdown/JSON）
5. 文件名策略

运行方式：
    python test_phase4_formatter.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List

from loguru import logger

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")


def test_section(name: str):
    """打印测试章节"""
    print("\n" + "="*70)
    print(f"  【测试】{name}")
    print("="*70 + "\n")


def test_result(name: str, success: bool, details: str = ""):
    """打印测试结果"""
    status = "✓ 通过" if success else "✗ 失败"
    print(f"  {status} - {name}")
    if details and not success:
        print(f"      详情: {details}")


# ============================================================================
# 测试 1: 文本清洗功能
# ============================================================================

def test_text_cleaner():
    """测试文本清洗器"""
    from core.formatter.text_cleaner import TextCleaner
    
    test_section("文本清洗功能")
    
    cleaner = TextCleaner(
        remove_fillers=True,
        remove_repetitions=True,
        fix_punctuation=True
    )
    
    # 测试1: 去除语气词
    text1 = "啊，我觉得呢，这个方案吧，应该可以。"
    result1 = cleaner.clean(text1)
    expected1 = "我觉得这个方案应该可以。"
    test_result(
        "去除语气词",
        result1 == expected1,
        f"期望: '{expected1}', 实际: '{result1}'"
    )
    
    # 测试2: 修复标点
    text2 = "你好！！！这个方案很好，，，你觉得呢？？"
    result2 = cleaner.clean(text2)
    test_result(
        "修复重复标点",
        "！！！" not in result2 and "，，" not in result2,
        f"结果: '{result2}'"
    )
    
    # 测试3: 综合清洗
    text3 = "嗯，这个，这个方案我觉得，嗯，非常好啊。"
    result3 = cleaner.clean(text3)
    test_result(
        "综合清洗",
        "嗯" not in result3 and result3.count("这个") == 1,
        f"结果: '{result3}'"
    )


# ============================================================================
# 测试 2: 格式化风格
# ============================================================================

def test_formatting_styles():
    """测试格式化风格"""
    from core.formatter.base import FormattedDocument, FormattingStyle
    from core.formatter.styles import RawStyle, CleanedStyle, ParagraphStyle
    
    test_section("格式化风格")
    
    # 测试数据
    test_text = """嗯，今天呢，我们讨论一下这个项目。
    我觉得呢，这个方案非常好，非常实用。
    然后，大家还有什么意见吗？
    我觉得我们应该尽快推进这个方案。"""
    
    # 1. 测试 RawStyle
    print("  测试 1: RawStyle（原始风格）")
    doc1 = FormattedDocument(raw_text=test_text, style=FormattingStyle.RAW)
    result1 = RawStyle().format(doc1)
    test_result(
        "RawStyle 保持原文",
        result1.formatted_text == test_text,
        None
    )
    print(f"      输出长度: {len(result1.formatted_text)} 字符\n")
    
    # 2. 测试 CleanedStyle
    print("  测试 2: CleanedStyle（清洗风格）")
    doc2 = FormattedDocument(raw_text=test_text, style=FormattingStyle.CLEANED)
    result2 = CleanedStyle().format(doc2)
    has_fillers = any(f in result2.formatted_text for f in ["嗯，", "呢，", "然后，"])
    test_result(
        "CleanedStyle 去除语气词",
        not has_fillers,
        f"结果: {result2.formatted_text[:100]}..."
    )
    print(f"      清洗后长度: {len(result2.formatted_text)} 字符\n")
    
    # 3. 测试 ParagraphStyle
    print("  测试 3: ParagraphStyle（段落风格）")
    doc3 = FormattedDocument(raw_text=test_text, style=FormattingStyle.PARAGRAPHS)
    result3 = ParagraphStyle(min_sentences=2).format(doc3)
    has_paragraphs = '\n\n' in result3.formatted_text
    test_result(
        "ParagraphStyle 分段",
        has_paragraphs,
        None
    )
    paragraphs = result3.formatted_text.split('\n\n')
    print(f"      分段数量: {len(paragraphs)}")
    for i, para in enumerate(paragraphs[:3], 1):
        preview = para[:50].replace('\n', ' ')
        print(f"        段落 {i}: {preview}...")
    print()


# ============================================================================
# 测试 3: 文件名策略
# ============================================================================

def test_naming_strategy():
    """测试文件名策略"""
    from core.formatter.naming import NamingStrategy, NamingTemplate
    
    test_section("文件名策略")
    
    # 1. 测试默认模板
    print("  测试 1: 默认模板")
    strategy1 = NamingStrategy(template="timestamp")
    filename1 = strategy1.generate(
        title="会议记录",
        session_id="sess_abc123"
    )
    test_result(
        "timestamp 模板",
        len(filename1) > 0 and filename1[0].isdigit(),
        f"结果: {filename1}"
    )
    print(f"      文件名: {filename1}\n")
    
    # 2. 测试自定义模板
    print("  测试 2: 自定义模板")
    strategy2 = NamingStrategy(template="{date}_{title}")
    filename2 = strategy2.generate(
        title="项目讨论会",
        timestamp=datetime(2024, 1, 15, 10, 30, 0)
    )
    test_result(
        "自定义模板 {date}_{title}",
        "20240115" in filename2 and "项目讨论会" in filename2,
        f"结果: {filename2}"
    )
    print(f"      文件名: {filename2}\n")
    
    # 3. 测试非法字符清理
    print("  测试 3: 非法字符清理")
    strategy3 = NamingStrategy()
    filename3 = strategy3.generate(
        title="会议：讨论<方案>版本1.0？",
        session_id="test"
    )
    has_illegal = any(c in filename3 for c in '<>:"/\\|?*')
    test_result(
        "非法字符清理",
        not has_illegal,
        f"结果: {filename3}"
    )
    print(f"      清理后: {filename3}\n")


# ============================================================================
# 测试 4: 导出器
# ============================================================================

def test_exporters():
    """测试导出器"""
    from core.formatter.base import FormattedDocument, FormattingStyle, BehaviorMatch
    from core.formatter.exporters import JSONExporter, MarkdownExporter
    
    test_section("文档导出功能")
    
    # 创建测试文档
    doc = FormattedDocument(
        title="测试会议记录",
        raw_text="今天讨论了项目进度。我觉得我们可以加快进度。真的吗？这样可以吗？",
        formatted_text="今天讨论了项目进度。我觉得我们可以加快进度。真的吗？这样可以吗？",
        style=FormattingStyle.CLEANED,
        session_id="test_session_001",
        word_count=45,
        duration_seconds=120.5,
        behavior_matches=[
            BehaviorMatch(
                behavior_name="质疑追问",
                original_text="真的吗？这样可以吗？",
                confidence=0.85,
                context_start=30,
                context_end=42
            )
        ],
        behaviors_config=["质疑追问", "建议"]
    )
    
    output_dir = Path("./output/test_phase4")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 测试 JSON 导出
    print("  测试 1: JSON 导出")
    try:
        json_exporter = JSONExporter()
        json_path = json_exporter.export(doc, output_dir / "test_document")
        test_result(
            "JSON 导出",
            json_path.exists() and json_path.suffix == ".json",
            None
        )
        print(f"      导出路径: {json_path}")
        
        # 验证JSON内容
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        test_result(
            "JSON 内容验证",
            data.get("title") == "测试会议记录" and "behavior_matches" in data,
            None
        )
        print()
    except Exception as e:
        test_result("JSON 导出", False, str(e))
        print()
    
    # 2. 测试 Markdown 导出
    print("  测试 2: Markdown 导出")
    try:
        md_exporter = MarkdownExporter()
        md_path = md_exporter.export(doc, output_dir / "test_document")
        test_result(
            "Markdown 导出",
            md_path.exists() and md_path.suffix == ".md",
            None
        )
        print(f"      导出路径: {md_path}")
        
        # 验证Markdown内容
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        test_result(
            "Markdown 内容验证",
            "# 测试会议记录" in content and "## 行为匹配结果" in content,
            None
        )
        # 显示部分内容
        lines = content.split('\n')
        print("      内容预览:")
        for line in lines[:8]:
            if line.strip():
                print(f"        {line[:60]}")
        print()
    except Exception as e:
        test_result("Markdown 导出", False, str(e))
        print()
    
    # 3. 测试 Word 导出（可选，需要 python-docx）
    print("  测试 3: Word 导出")
    try:
        from core.formatter.exporters import WordExporter
        word_exporter = WordExporter()
        word_path = word_exporter.export(doc, output_dir / "test_document")
        test_result(
            "Word 导出",
            word_path.exists() and word_path.suffix == ".docx",
            None
        )
        print(f"      导出路径: {word_path}")
        print()
    except ImportError:
        test_result(
            "Word 导出",
            False,
            "需要安装 python-docx: pip install python-docx"
        )
        print()
    except Exception as e:
        test_result("Word 导出", False, str(e))
        print()


# ============================================================================
# 主函数
# ============================================================================

def main():
    """主函数"""
    print("\n" + "="*70)
    print("  Phase 4 格式化模块测试")
    print("="*70)
    print()
    print("测试内容：")
    print("  1. 文本清洗功能")
    print("  2. 格式化风格（Raw/Cleaned/Paragraphs）")
    print("  3. 文件名策略")
    print("  4. 文档导出（JSON/Markdown/Word）")
    print()
    
    try:
        # 运行所有测试
        test_text_cleaner()
        test_formatting_styles()
        test_naming_strategy()
        test_exporters()
        
        # 测试总结
        print("\n" + "="*70)
        print("  Phase 4 测试完成")
        print("="*70)
        print()
        print("所有测试项已执行完成。")
        print("输出文件位于: ./output/test_phase4/")
        print()
        
    except Exception as e:
        logger.error(f"测试执行失败: {e}")
        raise


if __name__ == "__main__":
    main()
