"""审校辅助逻辑的离线回归测试。"""

from core.formatter.base import TranscriptionSegment
from core.review import add_revision, changed_ranges, clock_text, segment_ranges


def test_revisions_keep_original_and_recent_changes():
    revisions = []
    for number in range(30):
        revisions = add_revision(revisions, str(number), '修订')
    assert len(revisions) == 20
    assert revisions[0]['text'] == '0'
    assert [item['text'] for item in revisions[1:]] == [str(n) for n in range(11, 30)]
    assert add_revision(revisions, '29', '重复') == revisions


def test_short_comparison_highlights_only_changed_characters():
    assert changed_ranges('今天讨论项目进度。', '今天讨论交付进度。') == [('replace', 4, 6, 4, 6)]
    assert changed_ranges('原文', '') == [('delete', 0, 2, 0, 0)]
    assert changed_ranges('', '补充') == [('insert', 0, 0, 0, 2)]


def test_large_comparison_returns_correct_line_offsets():
    text = '首段。' * 10000 + '\n保留段落。\n'
    changes = changed_ranges(text, text + '新增结论。')
    assert changes == [('insert', len(text), len(text), len(text), len(text) + 5)]


def test_repeated_sentences_map_to_separate_occurrences():
    segments = [TranscriptionSegment(text, 0, 1) for text in ('好的', '缺失', '好的')]
    assert segment_ranges('好的。 好的。', segments) == [(0, 2), (-1, -1), (4, 6)]


def test_clock_supports_long_recordings():
    assert clock_text(-1) == '00:00'
    assert clock_text(3661) == '01:01:01'


def test_export_respects_intentionally_empty_draft(tmp_path):
    from core.formatter.base import FormattedDocument
    from core.formatter.exporters import MarkdownExporter, WordExporter
    from docx import Document
    document = FormattedDocument(raw_text='不应重新出现在正文的原文', formatted_text='', draft_edited=True)
    markdown = MarkdownExporter().export(document, tmp_path / 'empty.md')
    word = WordExporter().export(document, tmp_path / 'empty.docx')
    assert document.raw_text not in markdown.read_text(encoding='utf-8')
    assert all(document.raw_text not in paragraph.text for paragraph in Document(word).paragraphs)
