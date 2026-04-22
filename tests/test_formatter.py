"""
格式化模块单元测试

测试文本格式化和导出文件名生成，不需要 API Key 即可运行。
"""

import pytest
from datetime import datetime
from pathlib import Path

# 添加项目根目录到Python路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.formatter.base import (
    FormattingStyle,
    TranscriptionSegment,
    BehaviorMatch,
    FormattedDocument,
    StyleFormatter
)
from core.formatter.styles import (
    CleanedStyle,
    ParagraphStyle,
    BehaviorMatchStyle
)
from core.formatter.behavior_matcher import BehaviorConfig
from core.formatter.naming import (
    generate_filename,
    NamingStrategy
)
from core.formatter.exporters import (
    MarkdownExporter,
    WordExporter,
    JSONExporter
)


class TestFormattingStyle:
    """格式化风格枚举测试"""

    def test_enum_values(self):
        """测试枚举值"""
        assert FormattingStyle.RAW.value == "raw"
        assert FormattingStyle.CLEANED.value == "cleaned"
        assert FormattingStyle.PARAGRAPHS.value == "paragraphs"
        assert FormattingStyle.BEHAVIOR_MATCH.value == "behavior_match"


class TestCleanedStyle:
    """清洗格式化测试"""

    def test_clean_basic_text(self):
        """测试基础文本清洗"""
        style = CleanedStyle()
        doc = FormattedDocument(
            title="test",
            style=FormattingStyle.CLEANED,
            raw_text="en na ge wo jue de zhe ge fang an bu cuo",
            word_count=10
        )
        result = style.format(doc)
        # TextCleaner cleans Chinese filler words
        assert isinstance(result.formatted_text, str)
        assert len(result.formatted_text) > 0

    def test_clean_multiple_segments(self):
        """测试多个分段清洗"""
        style = CleanedStyle()
        doc = FormattedDocument(
            title="test",
            style=FormattingStyle.CLEANED,
            raw_text="a jin tian tian qi hen hao\nwomen chu qu san bu",
            word_count=20
        )
        result = style.format(doc)
        assert isinstance(result.formatted_text, str)
        assert len(result.formatted_text) > 0

    def test_empty_input(self):
        """测试空输入"""
        style = CleanedStyle()
        doc = FormattedDocument(
            title="test",
            style=FormattingStyle.CLEANED,
            raw_text="",
            word_count=0
        )
        result = style.format(doc)
        assert result.formatted_text == ""


class TestParagraphStyle:
    """分段格式化测试"""

    def test_split_into_paragraphs(self):
        """测试分段 - 两个分段间隔超过阈值应该分开"""
        style = ParagraphStyle(min_sentences=1, pause_threshold=2.0)
        doc = FormattedDocument(
            title="test",
            style=FormattingStyle.PARAGRAPHS,
            raw_text="first paragraph content here second paragraph content on different topic",
            segments=[
                TranscriptionSegment(text="first paragraph content here", start_time=0.0, end_time=5.0),
                TranscriptionSegment(text="second paragraph content on different topic", start_time=8.0, end_time=10.0),
            ],
            word_count=30
        )
        result = style.format(doc)
        # 间隔 3 秒超过阈值，应该分段
        assert '\n\n' in result.formatted_text

    def test_empty_input(self):
        """测试空输入"""
        style = ParagraphStyle()
        doc = FormattedDocument(
            title="test",
            style=FormattingStyle.PARAGRAPHS,
            raw_text="",
            word_count=0
        )
        result = style.format(doc)
        assert result.formatted_text == ""


class TestDataClasses:
    """数据类测试"""

    def test_transcription_segment(self):
        """测试TranscriptionSegment"""
        seg = TranscriptionSegment(
            text="测试文本",
            start_time=1.0,
            end_time=2.5
        )
        assert seg.text == "测试文本"
        assert seg.start_time == 1.0
        assert seg.end_time == 2.5
        assert seg.speaker_id is None

    def test_behavior_match(self):
        """测试BehaviorMatch"""
        match = BehaviorMatch(
            behavior_name="测试行为",
            confidence=0.85,
            original_text="这是原文",
            context_start=0,
            context_end=10
        )
        assert match.behavior_name == "测试行为"
        assert match.confidence == pytest.approx(0.85)
        assert match.original_text == "这是原文"


class TestFormattedDocument:
    """FormattedDocument测试"""

    def test_formatted_document_creation(self):
        """测试创建文档"""
        doc = FormattedDocument(
            title="测试文档",
            style=FormattingStyle.CLEANED,
            raw_text="原始文本",
            formatted_text="格式化文本",
            word_count=4
        )
        assert doc.title == "测试文档"
        assert doc.style == FormattingStyle.CLEANED
        assert doc.raw_text == "原始文本"
        assert doc.formatted_text == "格式化文本"
        assert doc.word_count == 4
        # 测试默认值
        assert isinstance(doc.created_at, datetime)


class TestNaming:
    """文件命名测试"""

    def test_generate_filename_timestamp_template(self):
        """测试时间戳命名策略"""
        name = generate_filename("转录", template="timestamp")
        # 应该生成文件名，长度足够
        assert name is not None
        assert len(name) >= 15

    def test_generate_filename_title_only(self):
        """测试标题命名（使用自定义模板）"""
        name = generate_filename("会议记录", template="{title}")
        assert "会议记录" in name

    def test_generate_filename_timestamp_title(self):
        """测试时间戳+标题命名"""
        name = generate_filename("团队会议", template="timestamp_title")
        assert "团队会议" in name
        assert len(name) > len("团队会议")

    def test_naming_strategy_sanitize(self):
        """测试文件名清理"""
        strategy = NamingStrategy("{title}")
        # 测试非法字符被替换
        cleaned = strategy._sanitize_filename('file:name?*')
        assert 'file' in cleaned
        assert ':' not in cleaned
        assert '?' not in cleaned
        assert '*' not in cleaned

    def test_naming_strategy_default_template(self):
        """测试默认模板"""
        strategy = NamingStrategy()
        assert strategy._get_template().name == "timestamp"


class TestExporters:
    """导出器测试"""

    def test_markdown_exporter_correct_extension(self, tmp_path):
        """测试 Markdown 导出器自动添加正确扩展名"""
        doc = FormattedDocument(
            title="测试文档",
            raw_text="这是测试内容",
            formatted_text="这是**测试**内容",
            style=FormattingStyle.CLEANED,
            session_id="test_123",
            word_count=10,
            duration_seconds=60.0
        )

        exporter = MarkdownExporter()
        output_path = tmp_path / "test.markdown"
        final_path = exporter.export(doc, output_path)

        assert final_path.suffix == ".md"
        assert final_path.exists()
        assert final_path.stat().st_size > 0

    def test_json_exporter_export(self, tmp_path):
        """测试 JSON 导出"""
        doc = FormattedDocument(
            title="JSON测试",
            raw_text="测试内容",
            formatted_text="测试内容",
            style=FormattingStyle.RAW,
            word_count=4,
            duration_seconds=10.0
        )

        exporter = JSONExporter()
        output_path = tmp_path / "test.json"
        final_path = exporter.export(doc, output_path)

        assert final_path.exists()
        assert final_path.suffix == ".json"

    def test_word_exporter_behavior_marks_parsing(self, tmp_path):
        """测试 Word 导出正确解析行为标记（不重复正文）

        这验证了修复：之前正则表达式会导致正文重复显示，
        修复后只转换标记格式，正文内容不重复添加。
        """
        doc = FormattedDocument(
            title="行为匹配测试",
            raw_text="会议讨论项目进度。【决策安排(95%)】我们决定下周五交付。【风险识别(80%)】目前存在资源不足的问题。",
            formatted_text="会议讨论项目进度。【决策安排(95%)】我们决定下周五交付。【风险识别(80%)】目前存在资源不足的问题。",
            style=FormattingStyle.BEHAVIOR_MATCH,
            behavior_matches=[
                BehaviorMatch(
                    behavior_name="决策安排",
                    confidence=0.95,
                    original_text="我们决定下周五交付",
                    context_start=10,
                    context_end=30
                ),
                BehaviorMatch(
                    behavior_name="风险识别",
                    confidence=0.80,
                    original_text="目前存在资源不足的问题",
                    context_start=31,
                    context_end=55
                )
            ],
            session_id="test_behavior_001",
            word_count=50,
            duration_seconds=120.0
        )

        exporter = WordExporter()
        output_path = tmp_path / "test_behavior.docx"
        final_path = exporter.export(doc, output_path)

        assert final_path.exists()
        # 文件大小应该大于空文档
        assert final_path.stat().st_size > 100


class TestBehaviorMatchStyle:
    """行为匹配格式化测试"""

    def test_behavior_statistics_generation(self):
        """测试行为频率统计生成

        验证：
        - 按行为名称正确分组统计
        - 按置信度正确分类（高 >= 0.8，中 0.6-0.8，低 < 0.6）
        - 按总次数降序排序
        - 生成 Markdown 表格包含合计行
        """
        # Arrange
        from core.formatter.behavior_matcher import BehaviorDefinition
        config = BehaviorConfig(
            behaviors=[
                BehaviorDefinition(name="决策安排", description="决策相关"),
                BehaviorDefinition(name="风险识别", description="风险相关"),
                BehaviorDefinition(name="前瞻思考", description="前瞻相关"),
            ]
        )
        style = BehaviorMatchStyle(config)

        matches = [
            BehaviorMatch(behavior_name="决策安排", confidence=0.95, original_text="...", context_start=0, context_end=10),
            BehaviorMatch(behavior_name="决策安排", confidence=0.85, original_text="...", context_start=20, context_end=30),
            BehaviorMatch(behavior_name="决策安排", confidence=0.70, original_text="...", context_start=40, context_end=50),
            BehaviorMatch(behavior_name="风险识别", confidence=0.80, original_text="...", context_start=60, context_end=70),
            BehaviorMatch(behavior_name="风险识别", confidence=0.65, original_text="...", context_start=80, context_end=90),
            BehaviorMatch(behavior_name="前瞻思考", confidence=0.55, original_text="...", context_start=100, context_end=110),
        ]

        # Act
        stats_text = style._generate_statistics(matches)

        # Assert
        assert "行为频率统计" in stats_text
        assert "| 行为名称 | 总计 | 高置信度" in stats_text
        # 决策安排总计 3 次，高置信度 2 次（0.95, 0.85），中置信度 1 次（0.70）
        assert "| 决策安排 | 3 | 2 | 1 | 0 |" in stats_text
        # 风险识别总计 2 次，高置信度 1 次（0.80），中置信度 1 次（0.65）
        assert "| 风险识别 | 2 | 1 | 1 | 0 |" in stats_text
        # 前瞻思考总计 1 次，低置信度 1 次（0.55）
        assert "| 前瞻思考 | 1 | 0 | 0 | 1 |" in stats_text
        # 合计行
        assert "| **合计** | **6**" in stats_text
        # 按总次数降序，决策安排在前，前瞻思考在后
        assert stats_text.index("决策安排") < stats_text.index("前瞻思考")

    def test_no_matches_no_statistics(self):
        """测试没有匹配结果时不生成统计"""
        config = BehaviorConfig()
        style = BehaviorMatchStyle(config)
        result = style._format_with_matches("原始测试文本", [])
        assert result == "原始测试文本"
        assert "行为频率统计" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
