"""
关键行为匹配模块

通过LLM识别转录文本中的关键行为，并做出标记。
支持用户自定义4-7个关键行为条目。
支持超长文本自动分块处理，避免上下文溢出。
"""

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable

from loguru import logger

from api.bailian_llm import BailianLLMClient
from core.formatter.base import FormattedDocument, FormattingStyle, StyleFormatter, BehaviorMatch


@dataclass
class BehaviorDefinition:
    """行为定义"""
    name: str                    # 行为名称（如"说服影响"）
    description: str           # 行为描述
    examples: List[str] = field(default_factory=list)  # 示例句子
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "examples": self.examples
        }


@dataclass
class BehaviorConfig:
    """
    行为匹配配置

    用户通过GUI配置的关键行为列表（4-7个条目）。
    """
    behaviors: List[BehaviorDefinition] = field(default_factory=list)
    min_confidence: float = 0.6    # 最小置信度阈值
    include_context: bool = True   # 是否包含上下文
    context_chars: int = 30      # 上下文字符数
    enable_paragraph_reorganization: bool = True  # 是否启用LLM段落整理
    auto_chunk_long_text: bool = True             # 是否自动分块处理超长文本

    def __post_init__(self):
        """验证配置"""
        if len(self.behaviors) < 1:
            logger.warning("行为列表为空，至少需要定义1个行为")
        elif len(self.behaviors) > 7:
            logger.warning(f"行为条目过多({len(self.behaviors)})，建议控制在4-7个")
    
    def validate(self) -> tuple[bool, str]:
        """
        验证配置有效性
        
        Returns:
            (是否有效, 错误信息)
        """
        if not self.behaviors:
            return False, "至少需要定义1个关键行为"
        
        if len(self.behaviors) > 10:
            return False, f"行为条目过多({len(self.behaviors)})，最多支持10个"
        
        # 检查行为名称重复
        names = [b.name for b in self.behaviors]
        if len(names) != len(set(names)):
            return False, "行为名称不能重复"
        
        # 检查空名称
        for behavior in self.behaviors:
            if not behavior.name or not behavior.name.strip():
                return False, "行为名称不能为空"
        
        return True, "配置有效"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "behaviors": [b.to_dict() for b in self.behaviors],
            "min_confidence": self.min_confidence,
            "include_context": self.include_context,
            "context_chars": self.context_chars,
            "enable_paragraph_reorganization": self.enable_paragraph_reorganization,
            "auto_chunk_long_text": self.auto_chunk_long_text
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BehaviorConfig":
        """从字典创建"""
        behaviors = [
            BehaviorDefinition(
                name=b["name"],
                description=b.get("description", ""),
                examples=b.get("examples", [])
            )
            for b in data.get("behaviors", [])
        ]
        
        return cls(
            behaviors=behaviors,
            min_confidence=data.get("min_confidence", 0.6),
            include_context=data.get("include_context", True),
            context_chars=data.get("context_chars", 30),
            enable_paragraph_reorganization=data.get("enable_paragraph_reorganization", True),
            auto_chunk_long_text=data.get("auto_chunk_long_text", True)
        )


class BehaviorMatcher:
    """
    行为匹配器

    使用LLM识别转录文本中的关键行为。
    支持超长文本自动分块处理，避免上下文溢出。
    """

    # LLM提示词模板
    SYSTEM_PROMPT = """你是一个专业的行为分析助手。你的任务是分析转录文本，识别其中是否符合预定义的关键行为。

分析要求：
1. 仔细阅读转录文本
2. 判断文本中是否体现了指定的关键行为
3. 对于匹配的行为，提取原文引用并评估置信度
4. 只输出JSON格式结果，不要有任何其他说明

输出格式必须是以下JSON数组：
[
  {
    "behavior_name": "行为名称",
    "matched": true/false,
    "original_text": "匹配的原文（如matched为false则为空）",
    "confidence": 0.85,
    "explanation": "简短说明为什么匹配"
  }
]"""

    # 超长文本处理配置
    MAX_TOKENS_PER_CHUNK = 10000  # 每块最大token数
    TOKEN_RATIO_CJK = 1.5  # 汉字token换算比例 (汉字≈1.5token)

    def __init__(
        self,
        config: BehaviorConfig,
        llm_client: Optional[BailianLLMClient] = None,
        auto_chunk_long_text: bool = True,
        max_tokens_per_chunk: int = None
    ):
        """
        初始化匹配器

        Args:
            config: 行为配置
            llm_client: LLM客户端，如未提供则自动创建
            auto_chunk_long_text: 是否自动分块处理超长文本
            max_tokens_per_chunk: 每块最大token数，默认10000
        """
        self.config = config
        self.llm = llm_client or BailianLLMClient()
        self.auto_chunk_long_text = auto_chunk_long_text
        if max_tokens_per_chunk:
            self.MAX_TOKENS_PER_CHUNK = max_tokens_per_chunk

        # 验证配置
        is_valid, error_msg = config.validate()
        if not is_valid:
            raise ValueError(f"行为配置无效: {error_msg}")

        logger.info(f"BehaviorMatcher初始化完成，配置了{len(config.behaviors)}个行为，"
                    f"自动分块: {auto_chunk_long_text}")
    
    def _build_prompt(self, text: str) -> str:
        """构建LLM提示词"""
        # 构建行为定义部分
        behaviors_desc = []
        for i, behavior in enumerate(self.config.behaviors, 1):
            desc = f"{i}. {behavior.name}"
            if behavior.description:
                desc += f" - {behavior.description}"
            if behavior.examples:
                desc += f"\n   示例: {'; '.join(behavior.examples[:2])}"
            behaviors_desc.append(desc)
        
        behaviors_text = '\n'.join(behaviors_desc)
        
        prompt = f"""请分析以下转录文本，识别是否包含以下关键行为：

【关键行为定义】
{behaviors_text}

【转录文本】
{text}

请按照系统指令中的JSON格式输出分析结果。"""
        
        return prompt

    def _estimate_tokens(self, text: str) -> int:
        """估算文本的token数（粗略估算）"""
        # 汉字约1.5token，英文约1token/word
        chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * self.TOKEN_RATIO_CJK + other_chars * 0.5)

    def _split_into_chunks(self, text: str) -> List[str]:
        """将超长文本分割为多个块，每个块控制在MAX_TOKENS_PER_CHUNK以内"""
        estimated_tokens = self._estimate_tokens(text)
        if estimated_tokens <= self.MAX_TOKENS_PER_CHUNK:
            return [text]

        # 按段落分割
        paragraphs = re.split(r'\n\s*\n', text)
        chunks = []
        current_chunk = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self._estimate_tokens(para)
            # 加上提示词占用的tokens（行为定义等约1K tokens）
            tokens_with_overhead = para_tokens + 1000

            if current_tokens + tokens_with_overhead > self.MAX_TOKENS_PER_CHUNK and current_chunk:
                # 当前块已满，保存
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_tokens = 0

            current_chunk.append(para)
            current_tokens += tokens_with_overhead

        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))

        logger.info(f"超长文本分块：估算 {estimated_tokens} tokens，分割为 {len(chunks)} 块")
        return chunks

    def _match_chunk(self, text: str, text_offset: int = 0) -> List[BehaviorMatch]:
        """匹配单个文本块，text_offset用于校正位置偏移"""
        prompt = self._build_prompt(text)

        # 调用LLM
        response = self.llm.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.3,  # 较低温度以获得更稳定的结果
            max_tokens=2000
        )

        # 解析JSON结果，校正位置偏移
        matches = self._parse_response(response, text)
        # 校正位置偏移（因为当前块在全文中的起始位置不是0）
        if text_offset > 0:
            for match in matches:
                match.context_start += text_offset
                match.context_end += text_offset

        return matches

    def match(self, text: str) -> List[BehaviorMatch]:
        """
        执行行为匹配

        自动检测超长文本，如果超过阈值会自动分块逐块匹配。

        Args:
            text: 转录文本

        Returns:
            行为匹配结果列表
        """
        if not text or not text.strip():
            return []

        if not self.config.behaviors:
            return []

        estimated_tokens = self._estimate_tokens(text)
        logger.debug(f"行为匹配输入估算: {estimated_tokens} tokens")

        # 检查是否需要分块
        if self.auto_chunk_long_text and estimated_tokens + 1000 > self.MAX_TOKENS_PER_CHUNK:
            # 超长文本，分块处理
            chunks = self._split_into_chunks(text)
            all_matches = []
            text_offset = 0

            for i, chunk in enumerate(chunks):
                logger.debug(f"处理第 {i+1}/{len(chunks)} 块，长度 {len(chunk)} 字符")
                chunk_matches = self._match_chunk(chunk, text_offset)
                all_matches.extend(chunk_matches)
                text_offset += len(chunk) + 2  # +2 是段落间的空行 \n\n

            logger.info(f"分块匹配完成，共找到 {len(all_matches)} 个行为匹配")
            return all_matches
        else:
            # 正常长度，整块处理
            try:
                return self._match_chunk(text, 0)
            except Exception as e:
                logger.error(f"行为匹配失败: {e}")
                return []
    
    def _parse_response(self, response: str, original_text: str) -> List[BehaviorMatch]:
        """解析LLM响应"""
        matches = []
        
        try:
            # 提取JSON部分（处理可能的额外文本）
            json_match = re.search(r'\[[\s\S]*\]', response)
            if not json_match:
                logger.warning(f"未找到JSON数组: {response[:200]}")
                return []
            
            data = json.loads(json_match.group())
            
            if not isinstance(data, list):
                logger.warning(f"JSON不是数组: {type(data)}")
                return []
            
            for item in data:
                # 只处理匹配的项目
                if not item.get("matched", False):
                    continue
                
                # 检查置信度
                confidence = item.get("confidence", 0.5)
                if confidence < self.config.min_confidence:
                    continue
                
                # 提取原文位置
                matched_text = item.get("original_text", "")
                context_start, context_end = self._find_context_position(
                    original_text, matched_text
                )
                
                match = BehaviorMatch(
                    behavior_name=item.get("behavior_name", "未知"),
                    original_text=matched_text,
                    confidence=confidence,
                    context_start=context_start,
                    context_end=context_end
                )
                
                matches.append(match)
            
            logger.info(f"解析到{len(matches)}个行为匹配")
            return matches
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return []
        except Exception as e:
            logger.error(f"解析响应失败: {e}")
            return []
    
    def _find_context_position(self, text: str, matched_text: str) -> tuple:
        """查找匹配文本在原文中的位置"""
        if not matched_text:
            return 0, len(text)
        
        # 尝试精确匹配
        idx = text.find(matched_text)
        if idx >= 0:
            return idx, idx + len(matched_text)
        
        # 尝试模糊匹配（去除空格和标点）
        # 使用ASCII标点集代替\p{P}以支持Windows系统
        punctuation = r'[.,;:!?\-\[\]{}()<>\/\\"\'\`~@#$%^&*()_+\-=|\\]'
        simplified_text = re.sub(rf'[\s{punctuation}]', '', text)
        simplified_match = re.sub(rf'[\s{punctuation}]', '', matched_text)
        
        if simplified_match and simplified_match in simplified_text:
            # 计算大致位置
            ratio = simplified_text.index(simplified_match) / len(simplified_text)
            start = int(len(text) * ratio)
            end = min(start + len(matched_text) + 10, len(text))
            return start, end
        
        # 默认返回全文
        return 0, len(text)


# 便捷函数

def match_behaviors(
    text: str,
    behaviors: List[BehaviorDefinition],
    min_confidence: float = 0.6
) -> List[BehaviorMatch]:
    """
    便捷函数：快速匹配行为
    
    Args:
        text: 转录文本
        behaviors: 行为定义列表
        min_confidence: 最小置信度
        
    Returns:
        匹配结果列表
    """
    config = BehaviorConfig(
        behaviors=behaviors,
        min_confidence=min_confidence
    )
    
    matcher = BehaviorMatcher(config)
    return matcher.match(text)
