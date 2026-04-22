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
    可选启用LLM语义分段，获得更符合语义的段落结构。
    """

    def __init__(
        self,
        min_sentences: int = 2,
        pause_threshold: float = 2.0,
        enable_llm_reorganization: bool = False
    ):
        """
        初始化段落风格

        Args:
            min_sentences: 每个段落最少句子数
            pause_threshold: 停顿阈值（秒），超过此间隔开启新段落
            enable_llm_reorganization: 是否启用LLM语义分段，
                启用后使用百炼大模型按语义重新整理段落，结果更自然但消耗Token
        """
        self.min_sentences = min_sentences
        self.pause_threshold = pause_threshold
        self.enable_llm_reorganization = enable_llm_reorganization

    @property
    def style(self) -> FormattingStyle:
        return FormattingStyle.PARAGRAPHS

    def format(self, document: FormattedDocument, **kwargs) -> FormattedDocument:
        """段落风格：按停顿分割成段落，可选LLM语义整理"""
        # 读取选项，允许kwargs覆盖
        enable_llm = kwargs.get(
            "enable_llm_reorganization",
            self.enable_llm_reorganization
        )

        # 先清洗文本
        cleaner = TextCleaner()
        cleaned_text = cleaner.clean(document.raw_text)

        # 处理流程
        if enable_llm and cleaned_text.strip():
            from api.bailian_llm import reorganize_paragraphs
            try:
                logger.info("开始LLM语义段落整理...")
                processed_text = reorganize_paragraphs(cleaned_text, language=document.language)
                logger.info("LLM段落整理完成")
                document.formatted_text = processed_text
            except Exception as e:
                logger.warning(f"LLM段落整理失败，回退到基于时间戳分割: {e}")
                # 回退到原始基于时间戳的方法
                paragraphs = split_into_paragraphs(
                    cleaned_text,
                    min_sentences=self.min_sentences,
                    pause_threshold=self.pause_threshold,
                    segments=document.segments if document.segments else None
                )
                document.formatted_text = '\n\n'.join(paragraphs)
        else:
            # 原始方法：基于时间戳分割
            paragraphs = split_into_paragraphs(
                cleaned_text,
                min_sentences=self.min_sentences,
                pause_threshold=self.pause_threshold,
                segments=document.segments if document.segments else None
            )
            document.formatted_text = '\n\n'.join(paragraphs)

        document.style = self.style
        document.word_count = len(document.formatted_text)

        return document


class BehaviorMatchStyle(StyleFormatter):
    """
    关键行为匹配风格

    使用LLM识别文本中的关键行为，并标注。
    支持逐步精细化处理：清洗 → 段落整理 → 行为匹配
    """

    def __init__(
        self,
        behavior_config: Optional[BehaviorConfig] = None,
        enable_paragraph_reorganization: bool = None,
        auto_chunk_long_text: bool = None
    ):
        """
        初始化行为匹配风格

        Args:
            behavior_config: 行为匹配配置
            enable_paragraph_reorganization: 是否启用LLM段落整理，
                如果为None则从behavior_config读取，默认启用
            auto_chunk_long_text: 是否自动分块处理超长文本，
                如果为None则从behavior_config读取，默认启用
        """
        self.behavior_config = behavior_config
        # 如果传入了配置，从配置读取选项
        if behavior_config is not None:
            self.enable_paragraph_reorganization = getattr(
                behavior_config, 'enable_paragraph_reorganization', True
            )
            self.auto_chunk_long_text = getattr(
                behavior_config, 'auto_chunk_long_text', True
            )
        else:
            self.enable_paragraph_reorganization = (
                enable_paragraph_reorganization if enable_paragraph_reorganization is not None else True
            )
            self.auto_chunk_long_text = (
                auto_chunk_long_text if auto_chunk_long_text is not None else True
            )
        self._matcher: Optional[BehaviorMatcher] = None

    @property
    def style(self) -> FormattingStyle:
        return FormattingStyle.BEHAVIOR_MATCH

    def format(self, document: FormattedDocument, **kwargs) -> FormattedDocument:
        """
        行为匹配风格：识别并标注关键行为

        处理流程：
        1. 清洗文本（去除语气词、重复）
        2. （可选）LLM段落整理，按语义重新分段
        3. 行为匹配，对整理后的文本识别关键行为
        """
        # 获取配置
        config = self.behavior_config
        if not config:
            config = kwargs.get("behavior_config")

        # 读取可选配置覆盖
        enable_para_reorg = kwargs.get(
            "enable_paragraph_reorganization",
            self.enable_paragraph_reorganization
        )
        auto_chunk = kwargs.get(
            "auto_chunk_long_text",
            self.auto_chunk_long_text
        )

        # 即使配置为空或没有行为，也保持行为匹配风格
        # 步骤1: 清洗文本
        cleaner = TextCleaner()
        cleaned_text = cleaner.clean(document.raw_text)

        # 步骤2: （可选）LLM段落整理
        from api.bailian_llm import reorganize_paragraphs
        processed_text = cleaned_text
        doc_language = document.language

        if enable_para_reorg and config and config.behaviors:
            try:
                logger.info("开始LLM段落整理...")
                processed_text = reorganize_paragraphs(cleaned_text, language=doc_language)
                logger.info("LLM段落整理完成")
            except Exception as e:
                logger.warning(f"LLM段落整理失败，使用清洗后原始文本: {e}")
                processed_text = cleaned_text

        # 步骤3: 如果有配置且有行为定义，执行行为匹配
        matches = []
        if config and config.behaviors:
            try:
                # 创建匹配器
                if not self._matcher or self._matcher.config != config or self._matcher.language != doc_language:
                    self._matcher = BehaviorMatcher(
                        config,
                        auto_chunk_long_text=auto_chunk,
                        language=doc_language
                    )

                # 执行行为匹配
                matches = self._matcher.match(processed_text)
            except Exception as e:
                logger.warning(f"行为匹配执行失败，使用处理后的原始文本: {e}")
                matches = []

        # 生成带标记的文本（即使没有匹配也保持风格）
        formatted_text = self._format_with_matches(processed_text, matches)

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
            # 没有匹配到任何行为，添加友好提示
            if text.strip() and self.behavior_config and self.behavior_config.behaviors:
                # 有文本且已配置行为，但没有匹配到
                text = text + "\n\n---\n*未识别到符合定义的关键行为*"
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

        # 添加行为频率统计汇总
        if matches:
            stats_text = self._generate_statistics(matches)
            result.append('\n\n' + stats_text)

        return ''.join(result)

    def _generate_statistics(self, matches: List[Any]) -> str:
        """生成行为频率统计汇总

        按行为名称分组，统计总次数和不同置信度区间的分布。
        置信度分类：高 (>= 0.8)、中 (0.6-0.8)、低 (< 0.6)
        """
        # 按行为名称分组统计
        stats = {}
        for match in matches:
            name = match.behavior_name
            if name not in stats:
                stats[name] = {'total': 0, 'high': 0, 'medium': 0, 'low': 0}

            stats[name]['total'] += 1
            conf = match.confidence
            if conf >= 0.8:
                stats[name]['high'] += 1
            elif conf >= 0.6:
                stats[name]['medium'] += 1
            else:
                stats[name]['low'] += 1

        # 按总次数降序排序
        sorted_stats = sorted(
            stats.items(),
            key=lambda x: x[1]['total'],
            reverse=True
        )

        # 生成汇总文本
        lines = ['---', '**行为频率统计**', '']
        lines.append('| 行为名称 | 总计 | 高置信度(≥0.8) | 中置信度(0.6-0.8) | 低置信度(<0.6) |')
        lines.append('|---------|-----:|---------------:|-----------------:|--------------:|')

        for name, count in sorted_stats:
            lines.append(
                f'| {name} | {count["total"]} | {count["high"]} | {count["medium"]} | {count["low"]} |'
            )

        total_all = sum(c['total'] for _, c in sorted_stats)
        high_all = sum(c['high'] for _, c in sorted_stats)
        medium_all = sum(c['medium'] for _, c in sorted_stats)
        low_all = sum(c['low'] for _, c in sorted_stats)
        lines.append(f'| **合计** | **{total_all}** | **{high_all}** | **{medium_all}** | **{low_all}** |')

        return '\n'.join(lines)


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
