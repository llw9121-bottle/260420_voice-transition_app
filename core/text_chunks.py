"""按自然边界分块，保持字符及顺序完整，便于还原引文偏移。"""


def split_text(text: str, max_chars: int) -> list[str]:
    if max_chars < 1:
        raise ValueError('分块长度必须大于零')
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            midpoint = start + max_chars // 2
            boundary = max(text.rfind(mark, midpoint, end) for mark in ('\n', '。', '！', '？', '.', '!', '?', ' '))
            if boundary >= midpoint:
                end = boundary + 1
        chunks.append(text[start:end])
        start = end
    return chunks
