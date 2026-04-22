"""
格式化服务基类

定义格式化服务的核心接口和数据结构。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class FormattingStyle(str, Enum):
    """格式化风格枚举"""
    RAW = "raw"                    # 原始转录
    CLEANED = "cleaned"            # 清洗版本
    PARAGRAPHS = "paragraphs"      # 段落结构
    BEHAVIOR_MATCH = "behavior_match"   # 关键行为匹配


@dataclass
class TranscriptionSegment:
    """转录片段"""
    text: str
    start_time: float  # 秒
    end_time: float
    speaker_id: Optional[str] = None
    confidence: float = 1.0


@dataclass
class BehaviorMatch:
    """行为匹配结果"""
    behavior_name: str           # 行为名称（如"说服影响"）
    original_text: str           # 原文引用
    confidence: float            # 置信度 0-1
    context_start: int           # 上下文起始位置
    context_end: int             # 上下文结束位置


@dataclass
class FormattedDocument:
    """格式化后的文档"""
    # 元数据
    title: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    style: FormattingStyle = FormattingStyle.RAW
    session_id: Optional[str] = None
    language: str = "zh"                        # 识别语言 (zh=en 等)

    # 内容
    raw_text: str = ""                          # 原始文本
    formatted_text: str = ""                    # 格式化后文本
    segments: List[TranscriptionSegment] = field(default_factory=list)

    # 行为匹配（仅在behavior风格时使用）
    behavior_matches: List[BehaviorMatch] = field(default_factory=list)
    behaviors_config: Optional[List[str]] = None  # 配置的行为列表

    # 统计
    word_count: int = 0
    duration_seconds: float = 0.0
    speaker_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "style": self.style.value,
            "session_id": self.session_id,
            "language": self.language,
            "raw_text": self.raw_text,
            "formatted_text": self.formatted_text,
            "segments": [
                {
                    "text": s.text,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "speaker_id": s.speaker_id,
                    "confidence": s.confidence,
                }
                for s in self.segments
            ],
            "behavior_matches": [
                {
                    "behavior_name": b.behavior_name,
                    "original_text": b.original_text,
                    "confidence": b.confidence,
                    "context_start": b.context_start,
                    "context_end": b.context_end,
                }
                for b in self.behavior_matches
            ],
            "behaviors_config": self.behaviors_config,
            "word_count": self.word_count,
            "duration_seconds": self.duration_seconds,
            "speaker_count": self.speaker_count,
        }


@runtime_checkable
class StyleFormatter(Protocol):
    """风格格式化器协议"""
    
    @property
    def style(self) -> FormattingStyle:
        """返回支持的风格"""
        ...
    
    def format(self, document: FormattedDocument, **kwargs) -> FormattedDocument:
        """格式化文档"""
        ...


class FormatterService:
    """
    格式化服务
    
    管理多种格式化风格，提供统一的格式化接口。
    """
    
    def __init__(self):
        self._formatters: Dict[FormattingStyle, StyleFormatter] = {}
    
    def register_formatter(self, formatter: StyleFormatter) -> None:
        """注册格式化器"""
        self._formatters[formatter.style] = formatter
    
    def format_document(
        self,
        document: FormattedDocument,
        style: Optional[FormattingStyle] = None,
        **kwargs
    ) -> FormattedDocument:
        """
        格式化文档
        
        Args:
            document: 待格式化的文档
            style: 目标风格，默认使用文档当前风格
            **kwargs: 额外参数传递给格式化器
            
        Returns:
            格式化后的文档
        """
        target_style = style or document.style
        
        if target_style not in self._formatters:
            raise ValueError(f"未注册的格式化风格: {target_style}")
        
        formatter = self._formatters[target_style]
        return formatter.format(document, **kwargs)
    
    def get_available_styles(self) -> List[FormattingStyle]:
        """获取可用的格式化风格列表"""
        return list(self._formatters.keys())
