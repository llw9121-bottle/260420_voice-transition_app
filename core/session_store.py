"""会话快照存储：原子写入，导出与录音结束均不删除原始会话。"""

import json
import os
import re
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from core.formatter.base import (
    BehaviorMatch, FormattedDocument, FormattingStyle, TranscriptionSegment,
)
from utils.exceptions import DocumentSaveException
from utils.logger import logger


class SessionStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def path_for(self, session_id: str) -> Path:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', session_id) or session_id in {'.', '..'}:
            raise ValueError('无效的会话标识')
        return self.directory / f'{session_id}.json'

    def save(self, snapshot: dict) -> Path:
        """先完整落盘，再替换旧快照；写入失败时保留上一份可恢复记录。"""
        path = self.path_for(snapshot['document']['session_id'])
        temporary = None
        with self._lock:
            try:
                with tempfile.NamedTemporaryFile(
                    mode='w', encoding='utf-8', dir=self.directory,
                    prefix=path.stem + '_', suffix='.tmp', delete=False,
                ) as handle:
                    temporary = Path(handle.name)
                    json.dump(snapshot, handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            except Exception as error:
                raise DocumentSaveException(
                    f'会话保存失败: {error}', file_path=str(path), reason=str(error),
                ) from error
            finally:
                if temporary and temporary.exists():
                    try:
                        temporary.unlink()
                    except OSError:
                        logger.warning(f'无法清理未完成的快照文件: {temporary.name}')
        return path

    def latest(self) -> dict | None:
        """跳过损坏快照，仍可恢复较早的有效会话。"""
        for path in sorted(self.directory.glob('*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                self.restore_document(data)
                return data
            except (ValueError, KeyError, TypeError, OSError):
                logger.warning(f'跳过无法恢复的会话: {path.name}')
        return None

    def load(self, session_id: str) -> dict:
        data = json.loads(self.path_for(session_id).read_text(encoding='utf-8'))
        self.restore_document(data)
        return data

    def list_sessions(self) -> list[dict]:
        """后台生成摘要和搜索文本，文档对象按需加载。"""
        rows = []
        for path in self.directory.glob('*.json'):
            try:
                data = self.load(path.stem)
                doc = data['document']
                rows.append({
                    'session_id': doc['session_id'], 'title': doc['title'],
                    'created_at': doc['created_at'], 'saved_at': data.get('saved_at', doc['created_at']),
                    'duration_seconds': doc.get('duration_seconds', 0),
                    'preview': doc.get('raw_text', '')[:300],
                    'search_text': doc['title'] + '\n' + doc.get('raw_text', ''),
                    'word_count': len(doc.get('raw_text', '')),
                })
            except (OSError, ValueError, KeyError, TypeError):
                logger.warning(f'跳过无法读取的会话: {path.name}')
        return sorted(rows, key=lambda row: row['saved_at'], reverse=True)

    @staticmethod
    def restore_document(snapshot: dict) -> FormattedDocument:
        data = dict(snapshot['document'])
        session_id = data.get('session_id')
        if not isinstance(session_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', session_id) or session_id in {'.', '..'}:
            raise ValueError('会话标识无效')
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['style'] = FormattingStyle(data['style'])
        data['segments'] = [TranscriptionSegment(**item) for item in data.get('segments', [])]
        data['behavior_matches'] = [BehaviorMatch(**item) for item in data.get('behavior_matches', [])]
        return FormattedDocument(**data)
