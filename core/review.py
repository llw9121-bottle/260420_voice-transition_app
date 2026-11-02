"""整理稿版本与原文对照，保持转录原文不可变。"""

from datetime import datetime
from difflib import SequenceMatcher
from uuid import uuid4


def add_revision(revisions: list[dict], text: str, label: str) -> list[dict]:
    if revisions and revisions[-1]['text'] == text:
        return revisions
    revision = {'id': uuid4().hex, 'created_at': datetime.now().isoformat(), 'label': label, 'text': text}
    # 保留第一版和最近十九版，避免反复整理造成快照无限膨胀。
    result = [*revisions, revision]
    return result if len(result) <= 20 else [result[0], *result[-19:]]


def changed_ranges(original: str, edited: str) -> list[tuple]:
    """短文精确比较，长文按行比较，限制逐字符比较的开销。"""
    if max(len(original), len(edited)) <= 2000:
        return [opcode for opcode in SequenceMatcher(None, original, edited, autojunk=False).get_opcodes()
                if opcode[0] != 'equal']
    left, right = original.splitlines(keepends=True), edited.splitlines(keepends=True)
    left_offsets, right_offsets = [0], [0]
    for line in left:
        left_offsets.append(left_offsets[-1] + len(line))
    for line in right:
        right_offsets.append(right_offsets[-1] + len(line))
    return [
        (tag, left_offsets[i], left_offsets[j], right_offsets[k], right_offsets[l])
        for tag, i, j, k, l in SequenceMatcher(None, left, right).get_opcodes()
        if tag != 'equal'
    ]


def segment_ranges(raw_text: str, segments: list) -> list[tuple[int, int]]:
    ranges, cursor = [], 0
    for segment in segments:
        start = raw_text.find(segment.text, cursor)
        if start < 0:
            ranges.append((-1, -1))
            continue
        end = start + len(segment.text)
        ranges.append((start, end))
        cursor = end
    return ranges


def clock_text(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02}' if hours else f'{minutes:02}:{seconds:02}'
