"""验证后台导出、真实扩展名覆盖检查与原子替换失败保护。"""

import threading
from datetime import datetime
from queue import Queue
from unittest.mock import Mock

import pytest

from core.formatter.base import FormattedDocument
from core.formatter.exporters import JSONExporter, MarkdownExporter, WordExporter
from core.formatter.naming import NamingStrategy
from gui.export_dialog import ExportDialog


@pytest.mark.parametrize('exporter', [JSONExporter(), MarkdownExporter(), WordExporter()])
def test_partial_write_failure_preserves_existing_export(exporter, tmp_path, monkeypatch):
    target = tmp_path / ('saved' + exporter.file_extension)
    target.write_bytes(b'old document')
    def fail(document, path):
        path.write_bytes(b'partial document')
        raise OSError('磁盘已满')
    monkeypatch.setattr(exporter, '_write', fail)
    with pytest.raises(OSError, match='磁盘已满'):
        exporter.export(FormattedDocument(raw_text='新文稿'), target)
    assert target.read_bytes() == b'old document'
    assert not list(tmp_path.glob('.export-*'))


def test_replace_failure_preserves_existing_export(tmp_path, monkeypatch):
    target = tmp_path / 'saved.md'
    target.write_text('旧文件', encoding='utf-8')
    monkeypatch.setattr('core.formatter.exporters.os.replace', Mock(side_effect=PermissionError('文件被占用')))
    with pytest.raises(PermissionError):
        MarkdownExporter().export(FormattedDocument(raw_text='新文稿'), target)
    assert target.read_text(encoding='utf-8') == '旧文件'
    assert not list(tmp_path.glob('.export-*'))


@pytest.fixture
def dialog(tmp_path, monkeypatch):
    instance = ExportDialog.__new__(ExportDialog)
    instance.window = Mock()
    instance.document = FormattedDocument(title='测试', session_id='export', raw_text='原文')
    instance.is_exporting = instance._closed = False
    instance._results = Queue(maxsize=1)
    instance._filename_time = datetime(2026, 11, 2)
    for name, value in [('export_format', 'markdown'), ('output_dir', str(tmp_path)),
                        ('filename_template', 'custom'), ('custom_filename', 'existing.md')]:
        variable = Mock()
        variable.get.return_value = value
        setattr(instance, name, variable)
    instance.export_status = Mock()
    instance.on_export = Mock()
    instance._save_last_output_dir = Mock()
    instance._set_exporting = lambda value: setattr(instance, 'is_exporting', value)
    for name in ('showinfo', 'showerror', 'showwarning', 'askyesno'):
        monkeypatch.setattr('gui.export_dialog.messagebox.' + name, Mock(return_value=False))
    return instance


def test_markdown_checks_actual_md_file_before_overwrite(dialog, tmp_path, monkeypatch):
    target = tmp_path / 'existing.md'
    target.write_text('保留', encoding='utf-8')
    export = Mock()
    monkeypatch.setattr(dialog, '_do_export', export)
    dialog._on_export()
    export.assert_not_called()
    assert dialog._export_path() == target
    assert target.read_text(encoding='utf-8') == '保留'


def test_export_worker_never_calls_tk_and_completion_runs_on_ui_thread(dialog, tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    worker_ids = []
    def export(path, format_type):
        worker_ids.append(threading.get_ident())
        entered.set()
        assert release.wait(2)
        return path
    monkeypatch.setattr(dialog, '_do_export', export)
    dialog._on_export()
    try:
        assert entered.wait(2)
        assert dialog.is_exporting
        dialog.window.reset_mock()
        dialog._on_export()  # 重复点击不能创建第二个任务。
        release.set()
        path, error = dialog._results.get(timeout=2)
        assert not dialog.window.mock_calls
        dialog._results.put((path, error))
        ui_ids = []
        dialog.on_export.side_effect = lambda path: ui_ids.append(threading.get_ident())
        dialog._poll_export()
        assert worker_ids != [threading.get_ident()]
        assert ui_ids == [threading.get_ident()]
        assert not dialog.is_exporting
        assert dialog._closed
    finally:
        release.set()


def test_export_error_keeps_dialog_open_and_retryable(dialog):
    dialog.is_exporting = True
    dialog._results.put((None, '目录不可写'))
    dialog._poll_export()
    assert not dialog.is_exporting
    assert not dialog._closed
    dialog.on_export.assert_not_called()
    dialog.window.destroy.assert_not_called()


@pytest.mark.parametrize('name', ['CON', 'nul.txt', 'COM1', 'lpt9.docx'])
def test_windows_reserved_names_are_safe(name):
    assert NamingStrategy._sanitize_filename(name).startswith('_')


def test_processing_warnings_survive_all_export_formats(tmp_path):
    from docx import Document
    import json
    warning = '行为分析未完成，请重试。'
    document = FormattedDocument(raw_text='原文', processing_warnings=[warning])
    markdown = MarkdownExporter().export(document, tmp_path / 'notice.md')
    word = WordExporter().export(document, tmp_path / 'notice.docx')
    data = JSONExporter().export(document, tmp_path / 'notice.json')
    assert warning in markdown.read_text(encoding='utf-8')
    assert any(warning in paragraph.text for paragraph in Document(word).paragraphs)
    assert json.loads(data.read_text(encoding='utf-8'))['processing_warnings'] == [warning]
