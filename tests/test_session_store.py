"""验证会话落盘、替换失败与恢复，不调用外部服务。"""

import json
import os
from datetime import datetime
from unittest.mock import patch

import pytest

from core.formatter.base import BehaviorMatch, FormattedDocument, FormattingStyle, TranscriptionSegment
from core.session_store import SessionStore
from utils.exceptions import DocumentSaveException


def snapshot(session_id='session_test', text='原始记录'):
    document = FormattedDocument(
        session_id=session_id, title='访谈', raw_text=text, language='en',
        created_at=datetime(2026, 11, 2, 12, 0), style=FormattingStyle.BEHAVIOR_MATCH,
        formatted_text='整理结果', duration_seconds=42,
        segments=[TranscriptionSegment(text=text, start_time=0, end_time=2)],
        behavior_matches=[BehaviorMatch('提问', text, 0.8, 0, len(text))],
        analysis_text='独立分析原文', analysis_fingerprint='fingerprint',
        analysis_model='qwen-plus', analysis_at='2026-11-02T12:00:00',
    )
    return {'version': 1, 'document': document.to_dict(), 'settings': {'save_audio': True},
            'audio_path': 'session_test.wav', 'state': 'saved'}


def test_round_trip_preserves_document_and_settings(tmp_path):
    store = SessionStore(tmp_path)
    data = snapshot()
    path = store.save(data)
    restored = store.restore_document(store.latest())
    assert restored.to_dict() == data['document']
    assert restored.analysis_fingerprint == 'fingerprint'
    assert restored.analysis_model == 'qwen-plus'
    assert store.latest()['settings'] == data['settings']
    assert path.exists()  # 打开或恢复均不删除快照。


def test_history_searches_full_raw_text_and_skips_corrupt_records(tmp_path):
    store = SessionStore(tmp_path)
    data = snapshot(text='内容' * 300 + '末尾关键词')
    data['document']['analysis_text'] = '独立分析原文'
    data['revisions'] = [{'text': '人工修改'}]
    store.save(data)
    (tmp_path / 'broken.json').write_text('{', encoding='utf-8')
    rows = store.list_sessions()
    assert len(rows) == 1
    assert '访谈' in rows[0]['search_text']
    assert '末尾关键词' in rows[0]['search_text']
    loaded = store.load('session_test')
    assert loaded['revisions'] == data['revisions']
    restored = store.restore_document(loaded)
    assert restored.analysis_text == '独立分析原文'
    assert restored.segments[0].timing_source == 'estimated'


def test_legacy_segment_defaults_to_estimated_timing(tmp_path):
    data = snapshot()
    data['document'].pop('analysis_text')
    data['document']['segments'][0].pop('timing_source')
    document = SessionStore(tmp_path).restore_document(data)
    assert document.analysis_text == ''
    assert document.segments[0].timing_source == 'estimated'


def test_replace_failure_preserves_previous_snapshot(tmp_path):
    store = SessionStore(tmp_path)
    path = store.save(snapshot(text='旧记录'))
    with patch('core.session_store.os.replace', side_effect=OSError('磁盘不可写')):
        with pytest.raises(DocumentSaveException):
            store.save(snapshot(text='新记录'))
    assert json.loads(path.read_text(encoding='utf-8'))['document']['raw_text'] == '旧记录'
    assert not list(tmp_path.glob('*.tmp'))


def test_serialization_failure_preserves_previous_snapshot(tmp_path):
    store = SessionStore(tmp_path)
    store.save(snapshot())
    data = snapshot()
    data['invalid'] = object()
    with pytest.raises(DocumentSaveException):
        store.save(data)
    assert store.latest()['document']['raw_text'] == '原始记录'


def test_corrupt_latest_falls_back_to_previous(tmp_path):
    store = SessionStore(tmp_path)
    old = store.save(snapshot())
    broken = tmp_path / 'broken.json'
    broken.write_text('{', encoding='utf-8')
    os.utime(old, (1, 1))
    assert store.latest()['document']['session_id'] == 'session_test'
    assert broken.exists()


@pytest.mark.parametrize('session_id', ['../escape', '..', '.', 'folder/file', 'C:\\escape'])
def test_rejects_unsafe_session_paths(tmp_path, session_id):
    with pytest.raises(ValueError):
        SessionStore(tmp_path).save(snapshot(session_id))
