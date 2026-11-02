"""无窗口测试应用生命周期，验证后台启停、保存顺序和关闭流程。"""

import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import app as app_module
from core.recording_state import RecordingState
from core.formatter.base import BehaviorMatch, FormattedDocument
from core.formatter.behavior_matcher import (
    BehaviorConfig, BehaviorDefinition, compute_analysis_fingerprint,
)


@pytest.fixture
def application(tmp_path, monkeypatch):
    window = Mock()
    window.get_asr_language.return_value = 'zh'
    window.get_vad_silence_ms.return_value = 400
    window.get_selected_device_index.return_value = 0
    window.get_save_audio.return_value = False
    window.get_selected_style.return_value = 'raw'
    window.style_var.get.return_value = 'raw'
    window.get_enable_llm_paragraphs.return_value = False
    window.is_scroll_lock_enabled.return_value = False
    transcriber = Mock()
    transcriber.last_error = ''
    transcriber.failed_audio_bytes = transcriber.unsent_audio_bytes = 0
    transcriber.recorder = SimpleNamespace(
        dropped_chunks=0, write_dropped_chunks=0, write_error=None, gaps=[],
        config=SimpleNamespace(sample_rate=16000, channels=1),
    )
    transcriber.start.return_value = True
    transcriber.stop.return_value = '最终文本'
    transcriber.get_duration.return_value = 3.0
    transcriber.get_audio_duration.return_value = 2.5
    transcriber.get_current_volume.return_value = 0.2
    monkeypatch.setattr(app_module, 'project_root', tmp_path)
    monkeypatch.setattr(app_module, 'MainWindow', lambda: window)
    monkeypatch.setattr(app_module, 'RealtimeTranscriber', lambda **kwargs: transcriber)
    monkeypatch.setattr(app_module.VoiceTranscriptionApp, '_check_api_configuration_on_startup', lambda self: None)
    monkeypatch.setattr(app_module.VoiceTranscriptionApp, '_check_unsaved_recording', lambda self: None)
    for name in ('showerror', 'showwarning', 'askyesno'):
        monkeypatch.setattr('tkinter.messagebox.' + name, Mock(return_value=False))
    instance = app_module.VoiceTranscriptionApp()
    instance._prompt_export = Mock()
    yield instance, window, transcriber
    instance.audio_player.close(wait=True)
    instance._storage.shutdown(wait=True)
    app_module.logger.remove()


def pump_until(application, condition, timeout=3):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        application._poll_ui_events()
        time.sleep(0.01)
    assert condition()


def test_connecting_does_not_claim_to_be_recording(application):
    instance, window, transcriber = application
    entered, release = threading.Event(), threading.Event()
    def start(**kwargs):
        entered.set()
        assert release.wait(2)
        return True
    transcriber.start.side_effect = start
    instance._on_start_recording()
    assert entered.wait(2)
    assert instance.recording_state == RecordingState.CONNECTING
    assert instance.is_recording is False
    release.set()
    pump_until(instance, lambda: instance.recording_state == RecordingState.RECORDING)


def test_failed_start_returns_to_retryable_state_without_stopping_or_formatting(application):
    instance, window, transcriber = application
    transcriber.start.return_value = False
    transcriber.last_error = '连接失败'
    instance._on_start_recording()
    pump_until(instance, lambda: instance.recording_state == RecordingState.ERROR)
    assert instance.is_recording is False
    transcriber.stop.assert_not_called()
    instance._prompt_export.assert_not_called()


def test_raw_snapshot_exists_before_formatting_and_export_keeps_it(application):
    instance, window, transcriber = application
    instance._on_start_recording()
    pump_until(instance, lambda: instance.recording_state == RecordingState.RECORDING)
    instance._update_transcription_data('第一句', True)
    transcriber.stop.side_effect = lambda: instance._update_transcription_data('最后一句', True) or '第一句 最后一句'
    original = instance._format_document
    checked = []
    def format_document():
        snapshot = instance.session_store.latest()
        assert snapshot['document']['raw_text'] == '第一句 最后一句'
        checked.append(True)
        original()
    instance._format_document = format_document
    instance._on_stop_recording()
    pump_until(instance, lambda: instance.recording_state == RecordingState.SAVED)
    assert checked
    instance._prompt_export.assert_called_once()
    instance._on_export_complete(instance.session_store.directory / 'export.md')
    instance._save_future.result(timeout=2)
    snapshot = instance.session_store.latest()
    assert snapshot['document']['raw_text'] == '第一句 最后一句'
    assert snapshot['document']['duration_seconds'] == 2.5
    assert snapshot['state'] == 'saved'
    assert snapshot['exported_paths']


def test_pause_keeps_autosave_active(application):
    instance, window, transcriber = application
    instance._on_start_recording()
    pump_until(instance, lambda: instance.recording_state == RecordingState.RECORDING)
    instance._on_pause_recording()
    assert instance.recording_state == RecordingState.PAUSED
    window.root.after.reset_mock()
    instance._auto_save_loop()
    assert any(call.args[0] == 5000 for call in window.root.after.call_args_list)
    instance._on_resume_recording()
    assert instance.recording_state == RecordingState.RECORDING


def test_closing_during_connection_waits_for_stop_and_save(application):
    instance, window, transcriber = application
    entered, release = threading.Event(), threading.Event()
    def start(**kwargs):
        entered.set()
        assert release.wait(2)
        return True
    transcriber.start.side_effect = start
    instance._on_start_recording()
    assert entered.wait(2)
    instance._on_close()
    assert not instance._closed
    release.set()
    pump_until(instance, lambda: instance._closed)
    transcriber.stop.assert_called_once()
    assert instance.session_store.latest() is not None
    window.close.assert_called_once()
    instance._prompt_export.assert_not_called()


def test_failed_required_save_keeps_window_open(application, monkeypatch):
    instance, window, transcriber = application
    instance.current_document = FormattedDocument(session_id='session_test', raw_text='原文')
    instance.confirmed_text = '原文'
    monkeypatch.setattr(instance.session_store, 'save', Mock(side_effect=OSError('磁盘已满')))
    instance._on_close()
    pump_until(instance, lambda: instance.recording_state == RecordingState.ERROR)
    assert not instance._closed
    assert not instance._closing
    assert instance.current_document.raw_text == '原文'
    window.close.assert_not_called()


def test_restore_preserves_language_analysis_and_audio_reference(application):
    instance, window, transcriber = application
    document = FormattedDocument(
        session_id='session_old', raw_text='raw', formatted_text='formatted',
        language='en', duration_seconds=12,
    )
    snapshot = {'version': 1, 'document': document.to_dict(), 'settings': {'save_audio': True},
                'audio_path': str(instance.session_store.directory / 'session_old.wav'),
                'audio_issues': {'network_dropped_chunks': 2}}
    instance.session_store.save(snapshot)
    instance._restore_unsaved_recording(snapshot)
    instance._save_future.result(timeout=2)
    assert instance.current_document.to_dict() == document.to_dict()
    assert instance.recording_state == RecordingState.SAVED
    assert instance.session_store.latest()['audio_issues']['network_dropped_chunks'] == 2


def test_background_callback_does_not_touch_tk(application):
    instance, window, transcriber = application
    instance.current_document = FormattedDocument(session_id='session_test')
    window.reset_mock()
    worker = threading.Thread(target=instance._update_transcription_data, args=('文本', True))
    worker.start()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert not window.mock_calls
    assert instance.current_document.raw_text == '文本'


def test_review_save_preserves_raw_and_undo_buffer(application):
    instance, window, _ = application
    instance.current_document = FormattedDocument(session_id='review', raw_text='原始转录', formatted_text='自动整理')
    window.workspace.get_draft.return_value = '人工修订'
    instance._commit_review()
    instance._save_future.result(timeout=2)
    snapshot = instance.session_store.load('review')
    assert snapshot['document']['raw_text'] == '原始转录'
    assert snapshot['document']['formatted_text'] == '人工修订'
    assert [item['text'] for item in snapshot['revisions']] == ['自动整理', '人工修订']
    window.show_document.assert_not_called()  # 保存不能重建编辑器并清空撤销记录。


def test_switch_saves_pending_draft_before_loading_session(application):
    instance, window, old_transcriber = application
    instance.current_document = FormattedDocument(session_id='before', raw_text='之前', formatted_text='整理')
    instance.transcriber = old_transcriber
    window.workspace.get_draft.return_value = '尚未触发防抖保存的编辑'
    target = FormattedDocument(session_id='after', raw_text='另一段原文', formatted_text='另一段整理稿')
    instance.session_store.save({'document': target.to_dict(), 'revisions': [None, {}]})
    instance._open_session('after')
    pump_until(instance, lambda: instance.current_document.session_id == 'after')
    assert instance.session_store.load('before')['document']['formatted_text'] == '尚未触发防抖保存的编辑'
    assert instance.transcriber is None
    assert instance._revisions == []
    assert instance._session_snapshot()['audio_issues'] == {}


def test_seek_backward_is_not_replaced_by_previous_player_position(application):
    instance, window, _ = application
    instance.current_document = FormattedDocument(session_id='review', duration_seconds=60)
    instance._audio_path = instance.session_store.directory / 'review.wav'
    instance._playback_position = 50
    with instance.audio_player._lock:
        instance.audio_player._state.update(position=50, duration=60)
    instance._seek_audio(10)
    instance._poll_playback()
    assert instance._playback_position == 10


def test_reprocess_preserves_previous_draft_and_rejects_stale_result(application):
    instance, window, _ = application
    instance.current_document = FormattedDocument(session_id='review', raw_text='原文', formatted_text='旧稿')
    window.workspace.get_draft.return_value = '人工修订'
    instance._reprocess_document()
    pump_until(instance, lambda: instance.recording_state == RecordingState.SAVED)
    assert instance.current_document.formatted_text == '原文'
    assert [item['text'] for item in instance._revisions] == ['旧稿', '人工修订', '原文']
    instance._on_format_complete(FormattedDocument(session_id='review', formatted_text='过期结果'), token=instance._format_token - 1)
    assert instance.current_document.formatted_text == '原文'


def test_reprocess_reuses_unchanged_behavior_analysis(application, monkeypatch):
    # Arrange
    instance, window, _ = application
    config = BehaviorConfig(behaviors=[BehaviorDefinition('建议', '提出建议')])
    instance.behavior_config = config
    window.get_selected_style.return_value = 'behavior_match'
    window.get_enable_llm_paragraphs.return_value = False
    text = '我建议先测试。'
    model = app_module.settings.api.bailian_model
    fingerprint = compute_analysis_fingerprint(
        text, config, model, 'zh',
        config.enable_paragraph_reorganization, config.auto_chunk_long_text,
    )
    instance.current_document = FormattedDocument(
        session_id='reuse', raw_text=text, formatted_text='旧稿',
        analysis_text=text, analysis_fingerprint=fingerprint,
        analysis_model=model, analysis_at='2026-11-02T12:00:00',
        behavior_matches=[BehaviorMatch('建议', '我建议先测试', 0.9, 0, 5)],
        behaviors_config=['建议'],
    )
    calls = []
    original_style = app_module.BehaviorMatchStyle

    class _RecordingStyle(original_style):
        def format(self, document, **kwargs):
            calls.append('format')
            return document

        def render_reused(self, document):
            calls.append('reuse')
            return super().render_reused(document)

    monkeypatch.setattr(app_module, 'BehaviorMatchStyle', _RecordingStyle)

    # Act
    instance._reprocess_document()
    pump_until(instance, lambda: instance.recording_state == RecordingState.SAVED)

    # Assert
    assert calls == ['reuse']
    assert '建议(90%)' in instance.current_document.formatted_text
    assert '复用上次分析' in instance.current_document.formatted_text


def test_export_captures_editor_and_passes_independent_copy(application, monkeypatch):
    instance, window, _ = application
    instance.current_document = FormattedDocument(session_id='review', raw_text='原文', formatted_text='旧稿')
    window.workspace.get_draft.return_value = '导出前最后修改'
    dialog = Mock()
    monkeypatch.setattr(app_module, 'ExportDialog', dialog)
    instance._on_export_document()
    exported = dialog.call_args.args[1]
    assert exported.formatted_text == '导出前最后修改'
    assert exported.raw_text == '原文'
    exported.formatted_text = '导出副本改动'
    assert instance.current_document.formatted_text == '导出前最后修改'


def test_recovered_autosaved_draft_gets_checkpoint_before_reprocessing(application):
    instance, window, _ = application
    instance.current_document = FormattedDocument(session_id='review', raw_text='原文', formatted_text='恢复的人工稿')
    instance._revisions = app_module.add_revision([], '初稿', '初始整理稿')
    window.workspace.get_draft.return_value = '恢复的人工稿'
    instance._reprocess_document()
    pump_until(instance, lambda: instance.recording_state == RecordingState.SAVED)
    assert [item['text'] for item in instance._revisions] == ['初稿', '恢复的人工稿', '原文']


def test_cancel_format_preserves_draft_and_blocks_duplicate_remote_work(application, monkeypatch):
    instance, window, _ = application
    instance.current_document = FormattedDocument(session_id='cancel', raw_text='原始转录', formatted_text='保留的修订稿')
    window.workspace.get_draft.return_value = '保留的修订稿'
    entered, release = threading.Event(), threading.Event()
    formatter = Mock()
    def format_document(document, context):
        entered.set()
        assert release.wait(2)
        document.formatted_text = '过期的 AI 结果'
        return document
    formatter.format.side_effect = format_document
    monkeypatch.setattr(app_module, 'RawStyle', lambda: formatter)
    instance._reprocess_document()
    pump_until(instance, entered.is_set)
    instance._cancel_format()
    assert instance.recording_state == RecordingState.SAVED
    assert instance.current_document.formatted_text == '保留的修订稿'
    instance._reprocess_document()
    assert formatter.format.call_count == 1
    release.set()
    instance._format_worker.join(timeout=2)
    instance._poll_ui_events()
    assert instance.current_document.raw_text == '原始转录'
    assert instance.current_document.formatted_text == '保留的修订稿'


def test_slow_disk_coalesces_draft_autosaves_and_keeps_latest_edit(application, monkeypatch):
    instance, window, _ = application
    instance.current_document = FormattedDocument(session_id='slow', raw_text='原文', formatted_text='初稿')
    entered, release = threading.Event(), threading.Event()
    writes = []
    save = instance.session_store.save
    def slow_save(snapshot):
        writes.append(snapshot['document']['formatted_text'])
        if len(writes) == 1:
            entered.set()
            assert release.wait(2)
        return save(snapshot)
    monkeypatch.setattr(instance.session_store, 'save', slow_save)
    instance._on_draft_changed('第一稿')
    assert entered.wait(2)
    for number in range(10):
        instance._on_draft_changed(f'修改 {number}')
    release.set()
    instance._save_future.result(timeout=2)
    instance._poll_ui_events()
    instance._save_future.result(timeout=2)
    assert writes == ['第一稿', '修改 9']
    assert instance.session_store.load('slow')['document']['formatted_text'] == '修改 9'


def test_close_waits_for_active_export(application):
    instance, window, _ = application
    instance._export_dialog = SimpleNamespace(is_exporting=True, window=Mock())
    instance._on_close()
    assert not instance._closing
    window.close.assert_not_called()
    instance._export_dialog.window.lift.assert_called_once()


def test_close_retries_incomplete_stop(application):
    instance, window, transcriber = application
    instance._on_start_recording()
    pump_until(instance, lambda: instance.recording_state == RecordingState.RECORDING)
    transcriber.stop.side_effect = [RuntimeError('发送仍在收尾'), '最终文本']
    instance._on_stop_recording()
    pump_until(instance, lambda: instance._stop_failed)
    assert instance.recording_state == RecordingState.STOPPING
    instance._on_close()
    pump_until(instance, lambda: instance._closed)
    assert transcriber.stop.call_count == 2


@pytest.mark.parametrize('state', list(RecordingState))
def test_window_buttons_follow_confirmed_lifecycle(state):
    from gui.main_window import MainWindow
    window = MainWindow.__new__(MainWindow)
    for name in ('start_btn', 'pause_btn', 'stop_btn', 'export_btn', 'device_menu',
                 'refresh_device_btn', 'language_menu', 'vad_slider', 'save_audio_switch',
                 'style_menu', 'llm_para_check', 'behavior_btn', 'api_settings_btn',
                 'set_recording_indicator', 'update_status'):
        setattr(window, name, Mock())
    window.set_recording_state(state)
    window.start_btn.configure.assert_called_with(state='disabled' if state.busy else 'normal')
    window.stop_btn.configure.assert_called_with(state='normal' if state.captures_audio else 'disabled')
    window.pause_btn.configure.assert_called_with(
        state='normal' if state.captures_audio else 'disabled',
        text='继续' if state == RecordingState.PAUSED else '暂停',
    )


def test_recording_indicator_keeps_only_one_timer():
    from gui.main_window import MainWindow
    window = MainWindow.__new__(MainWindow)
    window._is_recording_flashing = False
    window._recording_indicator_timer_id = None
    window.root = Mock()
    window.recording_indicator = Mock()
    window.set_recording_indicator(True)
    window.set_recording_indicator(True)
    window.root.after.assert_called_once()
    timer_id = window._recording_indicator_timer_id
    window.set_recording_indicator(False)
    window.root.after_cancel.assert_called_once_with(timer_id)
    assert window._recording_indicator_timer_id is None
