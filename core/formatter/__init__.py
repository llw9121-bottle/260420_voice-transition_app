"""
文档格式化模块

提供文本格式化、风格转换和文档导出功能。
支持多种格式风格和导出格式。
"""

from core.formatter.base import FormatterService, FormattedDocument, FormattingStyle, BehaviorMatch
from core.formatter.styles import StyleRegistry, RawStyle, CleanedStyle, ParagraphStyle, BehaviorMatchStyle
from core.formatter.text_cleaner import TextCleaner
from core.formatter.behavior_matcher import BehaviorMatcher, BehaviorConfig, BehaviorDefinition
from core.formatter.exporters import BaseExporter, JSONExporter, MarkdownExporter, WordExporter

__all__ = [
    # 基础类
    'FormatterService',
    'FormattedDocument',
    'FormattingStyle',
    'BehaviorMatch',
    # 风格
    'StyleRegistry',
    'RawStyle',
    'CleanedStyle',
    'ParagraphStyle',
    'BehaviorMatchStyle',
    # 工具
    'TextCleaner',
    'BehaviorMatcher',
    'BehaviorConfig',
    'BehaviorDefinition',
    # 导出器
    'BaseExporter',
    'JSONExporter',
    'MarkdownExporter',
    'WordExporter',
]
