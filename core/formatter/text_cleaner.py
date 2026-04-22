"""
文本清洗工具

提供文本预处理功能：去除语气词、重复词、格式化标点等。
"""

import re
from typing import List, Pattern, Set


class TextCleaner:
    """文本清洗器"""
    
    # 常见语气词
    FILLER_WORDS: Set[str] = {
        '啊', '呢', '吧', '吗', '嘛', '哦', '额', '呃',
        '嗯', '恩', '哎', '唉', '哈', '呀', '哇', '哟',
        '这个', '那个', '就是', '然后', '那么', '所以',
        ' basically', ' like', ' you know', ' um', ' uh',
    }
    
    # 重复标点
    REPEATED_PUNCT_PATTERN: Pattern = re.compile(r'([，。！？；：,;:!?])\1+')
    
    # 多余空格
    EXTRA_SPACE_PATTERN: Pattern = re.compile(r'\s+')
    
    # 开头结尾的填充词
    START_FILLER_PATTERN: Pattern = re.compile(
        r'^[（(]?(?:\s*)(?:啊|呢|吧|吗|嘛|哦|额|呃|嗯|恩|哎|唉|哈|呀|哇|哟)(?:[，, \t]+|)[）)）]?',
        re.IGNORECASE
    )
    
    def __init__(
        self,
        remove_fillers: bool = True,
        remove_repetitions: bool = True,
        fix_punctuation: bool = True,
        custom_fillers: List[str] = None
    ):
        """
        初始化清洗器
        
        Args:
            remove_fillers: 是否去除语气词
            remove_repetitions: 是否去除重复词
            fix_punctuation: 是否修复标点
            custom_fillers: 自定义填充词列表
        """
        self.remove_fillers = remove_fillers
        self.remove_repetitions = remove_repetitions
        self.fix_punctuation = fix_punctuation
        
        self.filler_words = set(self.FILLER_WORDS)
        if custom_fillers:
            self.filler_words.update(custom_fillers)
    
    def clean(self, text: str) -> str:
        """
        清洗文本
        
        Args:
            text: 原始文本
            
        Returns:
            清洗后的文本
        """
        if not text:
            return text
        
        result = text
        
        # 去除开头填充词
        if self.remove_fillers:
            result = self._remove_start_fillers(result)
            result = self._remove_inline_fillers(result)
        
        # 去除重复词
        if self.remove_repetitions:
            result = self._remove_repetitions(result)
        
        # 修复标点
        if self.fix_punctuation:
            result = self._fix_punctuation(result)
        
        # 标准化空格
        result = self._normalize_spaces(result)
        
        return result.strip()
    
    def _remove_start_fillers(self, text: str) -> str:
        """去除开头的填充词"""
        # 循环去除，处理多个连续填充词
        result = text
        for _ in range(3):  # 最多处理3层
            new_result = self.START_FILLER_PATTERN.sub('', result)
            if new_result == result:
                break
            result = new_result
        return result
    
    def _remove_inline_fillers(self, text: str) -> str:
        """去除行内填充词"""
        result = text
        
        for filler in self.filler_words:
            # 匹配独立的填充词（前后是标点或空格）
            pattern = rf'(?<=[\\s，。！？；：,;:!?])?{re.escape(filler)}(?=[\\s，。！？；：,;:!?])'
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)
        
        return result
    
    def _remove_repetitions(self, text: str) -> str:
        """去除重复词语（3次以上重复变为1次）"""
        # 找出连续重复的词或短句
        words = text.split()
        if not words:
            return text
        
        result = []
        prev_word = None
        repeat_count = 0
        
        for word in words:
            if word == prev_word:
                repeat_count += 1
                if repeat_count < 2:  # 最多保留2次重复
                    result.append(word)
            else:
                prev_word = word
                repeat_count = 0
                result.append(word)
        
        return ' '.join(result)
    
    def _fix_punctuation(self, text: str) -> str:
        """修复标点符号"""
        # 合并重复标点
        result = self.REPEATED_PUNCT_PATTERN.sub(r'\1', text)
        
        # 确保中文标点后有空格（可选）
        # result = re.sub(r'([。！？；：])([^\\s])', r'\1 \2', result)
        
        return result
    
    def _normalize_spaces(self, text: str) -> str:
        """标准化空格"""
        # 合并多个空格
        result = self.EXTRA_SPACE_PATTERN.sub(' ', text)
        return result
    
    @classmethod
    def quick_clean(cls, text: str) -> str:
        """快速清洗（使用默认配置）"""
        cleaner = cls()
        return cleaner.clean(text)


def split_into_paragraphs(
    text: str,
    min_sentences: int = 2,
    pause_threshold: float = 2.0,
    segments: List = None
) -> List[str]:
    """
    将文本分割成段落
    
    Args:
        text: 待分割文本
        min_sentences: 最小句子数
        pause_threshold: 停顿阈值（秒），基于时间戳
        segments: 带时间戳的片段列表
        
    Returns:
        段落列表
    """
    if not segments:
        # 没有时间戳，按句子分割
        sentences = re.split(r'([。！？\\.!?])', text)
        paragraphs = []
        current_para = []
        
        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else '')
            current_para.append(sentence)
            
            if len(current_para) >= min_sentences:
                paragraphs.append(''.join(current_para))
                current_para = []
        
        if current_para:
            paragraphs.append(''.join(current_para))
        
        return paragraphs if paragraphs else [text]
    
    # 有时间戳，按停顿分割
    paragraphs = []
    current_para = []
    last_end_time = 0.0
    
    for segment in segments:
        # 检查停顿
        if current_para and segment.start_time - last_end_time > pause_threshold:
            if len(current_para) >= min_sentences:
                paragraphs.append(''.join(current_para))
                current_para = []
        
        current_para.append(segment.text)
        last_end_time = segment.end_time
    
    if current_para:
        paragraphs.append(''.join(current_para))
    
    return paragraphs if paragraphs else [text]
