"""
格式化风格定义

定义不同的格式化风格，每种风格对应特定的格式化逻辑。
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from loguru import logger

from config.settings import settings
from core.formatter.base import FormattedDocument, FormattingStyle, StyleFormatter
from core.formatter.text_cleaner import TextCleaner, split_into_paragraphs
from core.formatter.behavior_matcher import (
    BehaviorMatcher, BehaviorConfig, compute_analysis_fingerprint,
)
from core.processing import ProcessingContext
from utils.exceptions import ProcessingCancelled


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
        context = kwargs.get('context') or ProcessingContext()
        context.report('正在清理口语与分段')
        # 读取选项，允许kwargs覆盖
        enable_llm = kwargs.get(
            "enable_llm_reorganization",
            self.enable_llm_reorganization
        )

        # 清洗是分段和 LLM 分析的共同前置步骤。
        cleaner = TextCleaner()
        cleaned_text = cleaner.clean(document.raw_text)

        if enable_llm and cleaned_text.strip():
            from api.bailian_llm import reorganize_paragraphs
            try:
                logger.info("开始LLM语义段落整理...")
                context.report('正在调用 AI 语义分段')
                processed_text = reorganize_paragraphs(cleaned_text, language=document.language, context=context)
                context.check()
                logger.info("LLM段落整理完成")
                document.formatted_text = processed_text
            except ProcessingCancelled:
                raise
            except Exception as e:
                logger.warning(f"LLM段落整理失败，回退到基于时间戳分割: {e}")
                document.processing_warnings.append(f'AI 语义分段失败，本次使用本地分段：{e}；可稍后重新整理。')
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
        self._reused = False
        self._analysis_model = ''
        self._analysis_at_display = ''

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
        self._reused = False
        self._analysis_model = ''
        self._analysis_at_display = ''
        # 获取配置
        context = kwargs.get('context') or ProcessingContext()
        context.report('正在清理口语')
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

        # 即使没有行为定义，也保留行为匹配风格和清洗结果。
        cleaner = TextCleaner()
        cleaned_text = cleaner.clean(document.raw_text)

        # 可选语义分段；失败时回退到清洗文本。
        from api.bailian_llm import reorganize_paragraphs
        processed_text = cleaned_text
        doc_language = document.language
        segmentation_ok = True

        if enable_para_reorg and config and config.behaviors:
            try:
                logger.info("开始LLM段落整理...")
                context.report('正在调用 AI 语义分段')
                processed_text = reorganize_paragraphs(cleaned_text, language=doc_language, context=context)
                context.check()
                logger.info("LLM段落整理完成")
            except ProcessingCancelled:
                raise
            except Exception as e:
                logger.warning(f"LLM段落整理失败，使用清洗后原始文本: {e}")
                document.processing_warnings.append(f'AI 语义分段失败，行为分析使用清洗后的文本：{e}')
                processed_text = cleaned_text
                segmentation_ok = False

        # 行为匹配
        matches = []
        stats = {}
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
                matches = self._matcher.match(processed_text, context=context)
                context.check()
                stats = getattr(self._matcher, 'last_stats', {})
                for warning in getattr(self._matcher, 'last_warnings', []):
                    if warning not in document.processing_warnings:
                        document.processing_warnings.append(warning)
                if stats.get('skipped_unlocatable'):
                    message = (
                        f"模型返回 {stats.get('returned', 0)} 条结果，"
                        f"其中 {stats['skipped_unlocatable']} 条引文无法定位，已跳过。"
                    )
                    if message not in document.processing_warnings:
                        document.processing_warnings.append(message)
                if stats.get('skipped_invalid'):
                    message = (
                        f"模型返回 {stats.get('returned', 0)} 条结果，"
                        f"其中 {stats['skipped_invalid']} 条字段或行为名无效，已跳过。"
                    )
                    if message not in document.processing_warnings:
                        document.processing_warnings.append(message)
                if stats.get('skipped_definition_examples'):
                    message = (
                        f"模型把 {stats['skipped_definition_examples']} 条行为定义示例当成了原文，"
                        "已忽略；其他匹配结果不受影响。"
                    )
                    if message not in document.processing_warnings:
                        document.processing_warnings.append(message)
            except ProcessingCancelled:
                raise
            except Exception as e:
                logger.warning(f"行为匹配执行失败，使用处理后的原始文本: {e}")
                document.processing_warnings.append(f'行为分析未完成；当前没有可用分析结果，请重试：{e}')
                matches = []
                stats = {'failed_chunks': 1, 'chunks': 1}
        elif not config or not config.behaviors:
            document.processing_warnings.append('尚未配置行为定义，本次仅清理文本，未执行行为分析。')

        # 记录分析元数据；只有完整成功的结果才允许后续复用。
        candidate_model = getattr(getattr(self._matcher, 'llm', None), 'model', '')
        matcher_model = (
            candidate_model
            if isinstance(candidate_model, str) and candidate_model
            else settings.api.bailian_model
        )
        analysis_time = datetime.now()
        self._analysis_model = matcher_model
        self._analysis_at_display = analysis_time.strftime('%Y-%m-%d %H:%M')
        cacheable = (
            bool(config and config.behaviors)
            and segmentation_ok
            and not stats.get('failed_chunks')
            and not stats.get('skipped_unlocatable')
        )
        if cacheable:
            document.analysis_fingerprint = compute_analysis_fingerprint(
                document.raw_text,
                config,
                matcher_model,
                doc_language,
                enable_para_reorg,
                auto_chunk,
            )
            document.analysis_model = matcher_model
            document.analysis_at = analysis_time.isoformat(timespec='seconds')
        else:
            document.analysis_fingerprint = ''
            document.analysis_model = ''
            document.analysis_at = ''

        # 生成带标记的文本（即使没有匹配也保持风格）
        context.report('正在生成整理稿与分析依据')
        if not matches and stats.get('failed_chunks'):
            formatted_text = processed_text + "\n\n---\n*行为分析未完成：部分或全部分块失败，请重试*"
        else:
            formatted_text = self._format_with_matches(processed_text, matches)

        document.formatted_text = formatted_text
        document.analysis_text = processed_text
        document.style = self.style
        document.behavior_matches = matches
        if config and config.behaviors:
            document.behaviors_config = [b.name for b in config.behaviors]
        document.word_count = len(document.formatted_text)

        return document

    def render_reused(self, document: FormattedDocument) -> FormattedDocument:
        """复用已有分析结果重新渲染，不调用任何远程模型。

        仅在原文、行为配置、模型和提示词版本均未变化时使用；调用方负责校验指纹。
        """
        if not document.analysis_text:
            raise ValueError('没有可复用的分析结果')

        self._reused = True
        self._analysis_model = document.analysis_model or settings.api.bailian_model
        self._analysis_at_display = (
            document.analysis_at.replace('T', ' ')[:16] if document.analysis_at else ''
        )
        document.formatted_text = self._format_with_matches(
            document.analysis_text, document.behavior_matches
        )
        document.style = self.style
        document.word_count = len(document.formatted_text)
        return document

    @staticmethod
    def _safe_marker(value: str) -> str:
        """避免行为名破坏正文标记。"""
        return (
            str(value)
            .replace('【', '〔')
            .replace('】', '〕')
            .replace('\n', ' ')
            .replace('\r', ' ')
        )

    @staticmethod
    def _safe_markdown(value: str) -> str:
        """避免行为名破坏 Markdown 表格。"""
        return (
            str(value)
            .replace('\\', '\\\\')
            .replace('|', '\\|')
            .replace('\n', ' ')
            .replace('\r', ' ')
        )

    def _format_with_matches(self, text: str, matches: List[Any]) -> str:
        """将匹配结果格式化为带标记的文本；重叠区间合并，避免正文重复。"""
        if not matches:
            # 有文本且已配置行为，但没有可定位的匹配
            if text.strip() and self.behavior_config and self.behavior_config.behaviors:
                if self._reused:
                    note = '未识别到可定位的关键行为（复用上次分析结果）。如需新的独立结果，请点击“重新分析”。'
                else:
                    note = '未识别到可定位的关键行为。LLM 判定具有随机性，可点击“重新分析”获取新的独立结果。'
                text = text + f"\n\n---\n*{note}*"
            return text

        sorted_matches = sorted(matches, key=lambda m: (m.context_start, m.context_end))
        clusters = []
        for match in sorted_matches:
            start = max(0, min(match.context_start, len(text)))
            end = max(start, min(match.context_end, len(text)))
            if end <= start:
                continue
            if clusters and start <= clusters[-1]['end']:
                clusters[-1]['end'] = max(clusters[-1]['end'], end)
                clusters[-1]['matches'].append(match)
            else:
                clusters.append({'start': start, 'end': end, 'matches': [match]})

        result = []
        last_end = 0
        for cluster in clusters:
            if cluster['start'] > last_end:
                result.append(text[last_end:cluster['start']])
            markers = ' + '.join(
                f"{self._safe_marker(item.behavior_name)}({item.confidence:.0%})"
                for item in cluster['matches']
            )
            result.append(f"【{markers}】{text[cluster['start']:cluster['end']]}")
            last_end = cluster['end']

        if last_end < len(text):
            result.append(text[last_end:])

        result.append('\n\n' + self._generate_statistics(matches))
        return ''.join(result)

    def _generate_statistics(self, matches: List[Any]) -> str:
        """生成行为频率统计汇总

        按行为名称分组，统计总次数和不同置信度区间的分布。
        频次为模型识别且可定位的不同引文数量，不是绝对行为次数。
        """
        min_confidence = getattr(self.behavior_config, 'min_confidence', 0.6)
        medium_threshold = min(max(min_confidence, 0.0), 0.8)

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
            elif conf >= medium_threshold:
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
        lines.append(
            f'| 行为名称 | 总计 | 高置信度(≥0.8) | '
            f'中置信度(≥{medium_threshold:.0%}) | 低置信度(<{min_confidence:.0%}) |'
        )
        lines.append('|---------|-----:|---------------:|-----------------:|--------------:|')

        for name, count in sorted_stats:
            lines.append(
                f'| {self._safe_markdown(name)} | {count["total"]} | '
                f'{count["high"]} | {count["medium"]} | {count["low"]} |'
            )

        total_all = sum(c['total'] for _, c in sorted_stats)
        high_all = sum(c['high'] for _, c in sorted_stats)
        medium_all = sum(c['medium'] for _, c in sorted_stats)
        low_all = sum(c['low'] for _, c in sorted_stats)
        lines.append(f'| **合计** | **{total_all}** | **{high_all}** | **{medium_all}** | **{low_all}** |')
        lines.append('')
        lines.append(
            f'*注：频次为模型识别且可在原文中定位的不同引文数量，非绝对行为次数；'
            f'置信度低于 {min_confidence:.0%} 的结果已过滤。*'
        )

        meta = []
        if self._analysis_model:
            meta.append(f'分析模型：{self._safe_markdown(self._analysis_model)}')
        if self._analysis_at_display:
            meta.append(f'分析时间：{self._analysis_at_display}')
        if meta:
            lines.append('')
            lines.append(f"*{' · '.join(meta)}。*")
        lines.append('')
        lines.append('*LLM 判定具有随机性，同一文本重复分析可能得到不同结果；建议结合原文复核。*')
        if self._reused:
            lines.append('*本结果复用上次分析；如需新的独立结果，请点击“重新分析”。*')

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
