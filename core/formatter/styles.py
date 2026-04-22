"""
格式化风格定义

定义不同的格式化风格，每种风格对应特定的格式化逻辑。
"""

from typing import Dict, List, Optional, Any

from loguru import logger

from core.formatter.base import FormattedDocument, FormattingStyle, StyleFormatter
from core.formatter.text_cleaner import TextCleaner, split_into_paragraphs
from core.formatter.behavior_matcher import BehaviorMatcher, BehaviorConfig


class RawStyle(StyleFormatter):
    """
    原始风格
    
    不做任何处理，直接输出原始转录文本。
    """
    
    @property
    def style(self) -> FormattingStyle:
        return FormattingStyle.RAW
    
    def format(self, document: FormattedDocument, **kwargs) -> FormattedDocument:
        """原始风格：不做处理"""
        document.formatted_text = document.raw_text
        document.style = self.style
        document.word_count = len(document.formatted_text)
        return document


class CleanedStyle(StyleFormatter):
    """
    清洗风格
    
    去除语气词、重复词，修复标点符号。
    """
    
    def __init__(
        self,
        remove_fillers: bool = True,
        remove_repetitions: bool = True,
        fix_punctuation: bool = True
    ):
        self.cleaner = TextCleaner(
            remove_fillers=remove_fillers,
            remove_repetitions=remove_repetitions,
            fix_punctuation=fix_punctuation
        )
    
    @property
    def style(self) -> FormattingStyle:
        return FormattingStyle.CLEANED
    
    def format(self, document: FormattedDocument, **kwargs) -> FormattedDocument:
        """清洗风格：去除语气词和重复"""
        document.formatted_text = self.cleaner.clean(document.raw_text)
        document.style = self.style
        
        # 更新字数统计
        document.word_count = len(document.formatted_text)
        
        return document


class ParagraphStyle(StyleFormatter):
    """
    段落结构风格
    
    按时间戳停顿分割成段落，适合长文本阅读。
    """
    
    def __init__(
        self,
        min_sentences: int = 2,
        pause_threshold: float = 2.0
    ):
        self.min_sentences = min_sentences
        self.pause_threshold = pause_threshold
    
    @property
    def style(self) -> FormattingStyle:
        return FormattingStyle.PARAGRAPHS
    
    def format(self, document: FormattedDocument, **kwargs) -> FormattedDocument:
        """段落风格：按停顿分割成段落"""
        # 先清洗文本
        cleaner = TextCleaner()
        cleaned_text = cleaner.clean(document.raw_text)
        
        # 分割成段落
        paragraphs = split_into_paragraphs(
            cleaned_text,
            min_sentences=self.min_sentences,
            pause_threshold=self.pause_threshold,
            segments=document.segments if document.segments else None
        )
        
        # 用空行连接段落
        document.formatted_text = '\n\n'.join(paragraphs)
        document.style = self.style
        document.word_count = len(document.formatted_text)

        return document


class BehaviorMatchStyle(StyleFormatter):
    """
    关键行为匹配风格
    
    使用LLM识别文本中的关键行为，并标注。
    """
    
    def __init__(self, behavior_config: Optional[BehaviorConfig] = None):
        self.behavior_config = behavior_config
        self._matcher: Optional[BehaviorMatcher] = None
    
    @property
    def style(self) -> FormattingStyle:
        return FormattingStyle.BEHAVIOR_MATCH
    
    def format(self, document: FormattedDocument, **kwargs) -> FormattedDocument:
        """行为匹配风格：识别并标注关键行为"""
        # 获取配置
        config = self.behavior_config
        if not config:
            config = kwargs.get("behavior_config")

        # 即使配置为空或没有行为，也保持行为匹配风格
        # 先清洗文本
        cleaner = TextCleaner()
        cleaned_text = cleaner.clean(document.raw_text)

        # 如果有配置且有行为定义，执行行为匹配
        matches = []
        if config and config.behaviors:
            try:
                # 创建匹配器
                if not self._matcher or self._matcher.config != config:
                    self._matcher = BehaviorMatcher(config)

                # 执行行为匹配
                matches = self._matcher.match(cleaned_text)
            except Exception as e:
                logger.warning(f"行为匹配执行失败，使用清洗后原始文本: {e}")
                matches = []

        # 生成带标记的文本（即使没有匹配也保持风格）
        formatted_text = self._format_with_matches(cleaned_text, matches)

        document.formatted_text = formatted_text
        document.style = self.style
        document.behavior_matches = matches
        if config and config.behaviors:
            document.behaviors_config = [b.name for b in config.behaviors]
        document.word_count = len(document.formatted_text)

        return document
    
    def _format_with_matches(self, text: str, matches: List[Any]) -> str:
        """将匹配结果格式化为带标记的文本"""
        if not matches:
            return text
        
        # 按位置排序
        sorted_matches = sorted(matches, key=lambda m: m.context_start)
        
        result = []
        last_end = 0
        
        for match in sorted_matches:
            # 添加匹配前的文本
            if match.context_start > last_end:
                result.append(text[last_end:match.context_start])
            
            # 添加上下文和标记
            context_end = min(match.context_end, len(text))
            matched_text = text[match.context_start:context_end]
            
            # 格式化标记
            marked = f"【{match.behavior_name}({match.confidence:.0%})】{matched_text}"
            result.append(marked)
            
            last_end = context_end
        
        # 添加剩余文本
        if last_end < len(text):
            result.append(text[last_end:])
        
        return ''.join(result)


class StyleRegistry:
    """
    风格注册表
    
    管理所有可用的格式化风格。
    """
    
    def __init__(self):
        self._styles: Dict[FormattingStyle, StyleFormatter] = {}
        self._register_default_styles()
    
    def _register_default_styles(self):
        """注册默认风格"""
        self.register(RawStyle())
        self.register(CleanedStyle())
        self.register(ParagraphStyle())
        self.register(BehaviorMatchStyle())
    
    def register(self, formatter: StyleFormatter) -> None:
        """注册风格"""
        self._styles[formatter.style] = formatter
    
    def get(self, style: FormattingStyle) -> Optional[StyleFormatter]:
        """获取风格格式化器"""
        return self._styles.get(style)
    
    def list_styles(self) -> List[FormattingStyle]:
        """列出所有可用风格"""
        return list(self._styles.keys())
    
    def get_style_info(self) -> Dict[str, str]:
        """获取风格信息说明"""
        info = {
            FormattingStyle.RAW: "原始转录，不做任何处理",
            FormattingStyle.CLEANED: "清洗版本，去除语气词和重复",
            FormattingStyle.PARAGRAPHS: "段落结构，按停顿分割成段落",
            FormattingStyle.BEHAVIOR_MATCH: "关键行为匹配，标注指定行为",
        }
        return {k.value: v for k, v in info.items() if k in self._styles or k == FormattingStyle.BEHAVIOR_MATCH}


# 全局注册表实例
style_registry = StyleRegistry()
