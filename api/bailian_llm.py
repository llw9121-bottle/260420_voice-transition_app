"""
阿里云百炼(Bailian)大模型客户端

用于文本格式化、行为匹配等LLM任务。
支持Qwen-Max、Qwen-Plus等模型。
"""

import json
from typing import Any, Dict, List, Optional, Callable

import requests
from loguru import logger

from config.settings import settings


class BailianLLMClient:
    """
    百炼大模型客户端
    
    用于：
    - 文本格式化
    - 关键行为匹配
    - 摘要生成
    """
    
    # 可用模型
    MODEL_QWEN_MAX = "qwen-max"
    MODEL_QWEN_PLUS = "qwen-plus"
    MODEL_QWEN_TURBO = "qwen-turbo"
    
    # API端点
    BASE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = MODEL_QWEN_PLUS,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ):
        """
        初始化客户端
        
        Args:
            api_key: API Key，默认从配置读取
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成token数
        """
        self.api_key = api_key or settings.api.get_bailian_api_key()
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        if not self.api_key:
            raise ValueError("API Key未设置")
        
        logger.debug(f"BailianLLMClient初始化完成，模型: {model}")
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        on_chunk: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        生成文本
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            temperature: 温度（覆盖默认值）
            max_tokens: 最大token数
            stream: 是否流式输出
            on_chunk: 流式回调函数
            
        Returns:
            生成的文本
        """
        messages = []
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        messages.append({
            "role": "user",
            "content": prompt
        })
        
        payload = {
            "model": self.model,
            "input": {
                "messages": messages
            },
            "parameters": {
                "temperature": temperature or self.temperature,
                "result_format": "message"
            }
        }
        
        if max_tokens or self.max_tokens:
            payload["parameters"]["max_tokens"] = max_tokens or self.max_tokens
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            if stream and on_chunk:
                return self._stream_generate(payload, headers, on_chunk)
            else:
                response = requests.post(
                    self.BASE_URL,
                    json=payload,
                    headers=headers,
                    timeout=120
                )
                response.raise_for_status()
                
                data = response.json()
                
                if "output" in data and "choices" in data["output"]:
                    return data["output"]["choices"][0]["message"]["content"]
                else:
                    logger.error(f"Unexpected response format: {data}")
                    raise ValueError("API返回格式异常")
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"API请求失败: {e}")
            raise
        except Exception as e:
            logger.error(f"生成失败: {e}")
            raise
    
    def _stream_generate(
        self,
        payload: dict,
        headers: dict,
        on_chunk: Callable[[str], None]
    ) -> str:
        """流式生成"""
        full_text = []
        
        try:
            response = requests.post(
                self.BASE_URL,
                json=payload,
                headers=headers,
                stream=True,
                timeout=120
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data:'):
                        data_str = line[5:].strip()
                        if data_str == '[DONE]':
                            break
                        try:
                            data = json.loads(data_str)
                            if "output" in data and "choices" in data["output"]:
                                delta = data["output"]["choices"][0].get("message", {}).get("content", "")
                                if delta:
                                    on_chunk(delta)
                                    full_text.append(delta)
                        except json.JSONDecodeError:
                            continue
            
            return ''.join(full_text)
            
        except Exception as e:
            logger.error(f"流式生成失败: {e}")
            raise


class LLMFormatter:
    """
    LLM格式化工具
    
    封装常见的格式化任务。
    """
    
    def __init__(self, client: Optional[BailianLLMClient] = None):
        self.client = client or BailianLLMClient()
    
    def format_text(
        self,
        text: str,
        style: str = "standard",
        instructions: Optional[str] = None
    ) -> str:
        """
        格式化文本
        
        Args:
            text: 原始文本
            style: 格式化风格 (standard/formal/concise/casual)
            instructions: 额外指令
            
        Returns:
            格式化后的文本
        """
        style_prompts = {
            "standard": "请对以下文本进行标准化格式化，去除冗余内容，保持原意：",
            "formal": "请将以下文本转换为正式书面语，适合正式场合：",
            "concise": "请将以下文本精简，保留核心信息：",
            "casual": "请将以下文本转换为轻松自然的口语风格：",
        }
        
        prompt = style_prompts.get(style, style_prompts["standard"])
        
        if instructions:
            prompt += f"\n额外要求：{instructions}"
        
        prompt += f"\n\n原文：\n{text}"
        
        return self.client.generate(
            prompt=prompt,
            system_prompt="你是一个专业的文本格式化助手。"
        )
    
    def generate_summary(
        self,
        text: str,
        max_length: int = 200,
        style: str = "concise"
    ) -> str:
        """
        生成摘要
        
        Args:
            text: 原文
            max_length: 最大长度
            style: 摘要风格 (concise/detailed/key_points)
            
        Returns:
            摘要文本
        """
        style_prompts = {
            "concise": f"请用不超过{max_length}字概括以下内容的核心要点：",
            "detailed": f"请总结以下内容，保留关键信息，长度控制在{max_length}字左右：",
            "key_points": f"请提取以下内容的关键要点，用条目列出：",
        }
        
        prompt = style_prompts.get(style, style_prompts["concise"])
        prompt += f"\n\n{text}"
        
        return self.client.generate(prompt=prompt)


# 便捷函数

def quick_format(text: str, style: str = "standard") -> str:
    """快速格式化文本"""
    formatter = LLMFormatter()
    return formatter.format_text(text, style=style)


def quick_summary(text: str, max_length: int = 200) -> str:
    """快速生成摘要"""
    formatter = LLMFormatter()
    return formatter.generate_summary(text, max_length=max_length)


def reorganize_paragraphs(text: str, language: str = "zh") -> str:
    """
    使用LLM整理文本段落

    将原始转录文本按照语义重新整理为自然段落，
    保持原意不变，只优化段落结构。

    Args:
        text: 原始清洗后的文本
        language: 文本语言 (zh=中文, en=英文 等)，用于选择对应提示词

    Returns:
        整理后的分段文本（段落间用空行分隔）
    """
    client = BailianLLMClient()

    # 根据语言选择对应提示词
    if language.startswith("en"):
        # English prompt
        system_prompt = """You are a professional text reorganization assistant. Your task is to reorganize the transcribed text into natural paragraphs according to semantics.

【Core Requirements】
- You are only responsible for paragraph splitting, you are NOT allowed to modify, condense, summarize or rewrite any content
- You must **keep every word of the original text intact**, strictly forbidden to add, delete, or rewrite anything
- You must strictly preserve the original order of all sentences, do not adjust word order

Paragraph Splitting Rules:
1. Split the text into appropriate paragraphs according to semantic logic
2. Separate paragraphs with blank lines
3. Only output the reorganized text, do not add any other explanation
4. Do not fix colloquialisms, keep the original speaking style intact"""

        user_prompt = f"""Please only reorganize the paragraph structure of the following text according to the requirements, **keep all original content intact**:

{text}"""
    else:
        # Chinese prompt (default)
        system_prompt = """你是一个专业的文本整理助手。你的任务是将转录文本按照语义重新整理为自然段落。

【核心要求】
- 你只负责分段，不允许修改、浓缩、归纳原文内容
- 必须**完整保留原文的每一个字**，严格禁止增加、删除、改写任何内容
- 必须严格保留原文的所有语句顺序，不得调整语序

分段规则：
1. 根据语义逻辑将文本分割为合适的段落
2. 段落之间用空行分隔
3. 只输出整理后的文本，不要有任何其他说明
4. 不修正口语化表达，完整保留原始说话风格"""

        user_prompt = f"""请按照要求仅对以下文本进行分段整理，**完整保留所有原文内容**：

{text}"""

    return client.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.3,
        max_tokens=len(text) // 2 + 1000
    )


def reorganize_paragraphs_chunked(paragraphs: list[str], language: str = "zh") -> list[str]:
    """
    逐段整理多个段落

    Args:
        paragraphs: 原始段落列表
        language: 文本语言 (zh=中文, en=英文 等)，用于选择对应提示词

    Returns:
        整理后的段落列表
    """
    results = []
    for para in paragraphs:
        if not para.strip():
            results.append(para)
            continue
        result = reorganize_paragraphs(para, language=language)
        results.append(result.strip())
    return results
