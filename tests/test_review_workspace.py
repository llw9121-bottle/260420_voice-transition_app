"""显式启用的原生 Tk 工作区冒烟测试，不访问声卡或 API。"""

import os
from unittest.mock import Mock

import pytest

from core.formatter.base import FormattedDocument, TranscriptionSegment
from core.recording_state import RecordingState
from gui.main_window import MainWindow
from gui.session_history_dialog import SessionHistoryDialog


pytestmark = pytest.mark.skipif(os.getenv('RUN_GUI_TESTS') != '1', reason='设置 RUN_GUI_TESTS=1 并配置 Tk 后运行')


@pytest.fixture(scope='module')
def window():
    patch = pytest.MonkeyPatch()
    patch.setattr(MainWindow, '_load_user_config', lambda self: {'appearance_mode': 'Light'})
    patch.setattr(MainWindow, '_save_user_config', lambda self: None)
    patch.setattr(MainWindow, '_refresh_devices', lambda self: None)
    main = MainWindow()
    errors = []
    main.root.report_callback_exception = lambda *error: errors.append(error)
    yield main
    main.root.update()
    main.root.destroy()
    patch.undo()
    assert not errors


def test_native_editor_comparison_and_state_restore(window):
    document = FormattedDocument(session_id='gui', raw_text='第一句。 第二句。', formatted_text='第一段。')
    document.segments = [TranscriptionSegment('第一句。', 0, 2)]
    window.show_document(document, [], True)
    window.set_recording_state(RecordingState.SAVED)
    workspace = window.workspace
    workspace.draft_text.insert('end', '补充')
    window.root.update()
    workspace.refresh_revisions([])
    workspace._undo(False)
    assert workspace.get_draft() == '第一段。'
    assert document.raw_text == '第一句。 第二句。'
    workspace.tabs.set('对照')
    workspace._on_tab()
    assert workspace.compare_raw.tag_ranges('changed')
    workspace.search_entry.insert(0, '第一')
    workspace.search()
    workspace.search_next()
    assert workspace.search_count.cget('text') == '1/1'
    window.set_recording_state(RecordingState.PROCESSING)
    assert workspace.play_btn.cget('state') == 'disabled'
    window.set_recording_state(RecordingState.SAVED)
    assert workspace.play_btn.cget('state') == 'normal'


def test_incremental_live_text_and_compact_layout(window):
    workspace = window.workspace
    window.show_document(FormattedDocument(session_id='live'), [])
    window.set_recording_state(RecordingState.RECORDING)
    workspace.render_live('确认 ', '临时', [])
    workspace.render_live('确认 新句 ', '句尾', [])
    assert workspace.raw_text.get('1.0', 'end-1c') == '确认 新句 句尾'
    assert workspace.document.segments == []
    window.root.geometry('840x640')
    window.root.update()
    assert not workspace._sidebar_visible
    assert workspace.draft_text._textbox.cget('state') == 'disabled'
    assert window.export_btn.winfo_x() + window.export_btn.winfo_width() <= window.button_frame.winfo_width()
    window.root.geometry('1280x840')
    window.root.update()
    assert workspace._sidebar_visible
    window.set_recording_state(RecordingState.SAVED)


def test_history_search_and_style_restore(window):
    window.set_review_style('paragraphs', True)
    assert window.get_selected_style() == 'paragraphs'
    assert window.get_enable_llm_paragraphs()
    callback = Mock()
    dialog = SessionHistoryDialog(window.root, [{'session_id': 'a', 'title': '会议', 'created_at': '2026-11-02',
                                                'duration_seconds': 30, 'word_count': 10, 'search_text': '会议结论'}], callback)
    window.root.update()
    dialog.search.insert(0, '不存在')
    dialog._filter()
    assert '共 0 个会话' in dialog.count.cget('text')
    dialog._open('a')
    callback.assert_called_once_with('a')


def test_processing_progress_and_warning_are_visible(window):
    workspace = window.workspace
    document = FormattedDocument(session_id='warning', raw_text='原文', formatted_text='本地整理稿',
                                  processing_warnings=['AI 分段失败，本次使用本地分段。'])
    window.show_document(document, [])
    window.set_recording_state(RecordingState.PROCESSING)
    workspace.show_processing('正在分析行为：第 2/3 块', cancellable=True)
    window.root.update()
    assert workspace.processing_frame.winfo_ismapped()
    assert workspace.cancel_processing_btn.cget('state') == 'normal'
    assert '本地分段' in workspace.warning_label.cget('text')
    workspace.show_processing('正在保存整理结果…', cancellable=False)
    assert workspace.cancel_processing_btn.cget('state') == 'disabled'
    window.set_recording_state(RecordingState.SAVED)
    workspace.show_processing(None)
    window.root.update()
    assert not workspace.processing_frame.winfo_ismapped()


def test_export_dialog_has_actual_path_preview_and_fixed_actions(window, tmp_path, monkeypatch):
    from gui.export_dialog import ExportDialog
    monkeypatch.setattr(ExportDialog, '_load_last_output_dir', lambda self: str(tmp_path))
    dialog = ExportDialog(window.root, FormattedDocument(title='导出测试', raw_text='原文'))
    window.root.update()
    assert dialog._export_path().suffix == '.md'
    assert '.md' in dialog.path_preview.cget('text')
    dialog.window.geometry('580x550')
    window.root.update()
    assert dialog.export_btn.winfo_ismapped()
    assert dialog.export_btn.winfo_toplevel() == dialog.window
    dialog._on_cancel()


def test_native_background_export_keeps_event_loop_responsive(window, tmp_path, monkeypatch):
    import json
    import threading
    import time
    from gui.export_dialog import ExportDialog
    monkeypatch.setattr(ExportDialog, '_load_last_output_dir', lambda self: str(tmp_path))
    monkeypatch.setattr(ExportDialog, '_save_last_output_dir', lambda *args: None)
    monkeypatch.setattr('gui.export_dialog.messagebox.showinfo', Mock())
    callback = Mock()
    dialog = ExportDialog(window.root, FormattedDocument(title='后台导出', raw_text='原始文稿'), callback)
    dialog.export_format.set('json')
    path = dialog._export_path()
    release = threading.Event()
    export = dialog._do_export
    def delayed_export(*args):
        assert release.wait(2)
        return export(*args)
    monkeypatch.setattr(dialog, '_do_export', delayed_export)
    window.root.after(50, release.set)
    dialog._on_export()
    deadline = time.monotonic() + 3
    while not dialog._closed and time.monotonic() < deadline:
        window.root.update()
        time.sleep(0.01)
    release.set()
    assert dialog._closed
    assert json.loads(path.read_text(encoding='utf-8'))['raw_text'] == '原始文稿'
    callback.assert_called_once_with(path)
