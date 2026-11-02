"""
阿里云百炼(Bailian)大模型客户端

用于文本格式化、行为匹配等LLM任务。
支持Qwen-Max、Qwen-Plus等模型。
"""

import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Callable

import requests
from loguru import logger

from config.settings import preview_llm_content, settings
from utils.exceptions import BailianAPIException
from utils.proxy import bypass_proxy_for, should_fallback_to_direct


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
    
    # API路径；域名由配置按地域/业务空间推导
    GENERATION_PATH = "/services/aigc/text-generation/generation"

    @property
    def base_url(self) -> str:
        """按当前配置返回文本生成接口地址。"""
        return settings.api.http_base_url.rstrip('/') + self.GENERATION_PATH

    @staticmethod
    def _parse_error_body(response: requests.Response) -> tuple[str, str]:
        """提取 DashScope 原生/兼容格式的错误码和消息。"""
        try:
            data = response.json()
        except ValueError:
            return "", (response.text or "").strip()[:300]
        error = data.get("error") if isinstance(data.get("error"), dict) else {}
        code = data.get("code") or error.get("code") or ""
        message = data.get("message") or error.get("message") or ""
        return str(code), str(message)

    @classmethod
    def _raise_for_http_error(cls, response: requests.Response) -> None:
        """把 HTTP 错误转换为带可操作提示的异常。"""
        if response.status_code < 400:
            return
        code, message = cls._parse_error_body(response)
        lowered = message.lower()
        if code == "AllocationQuota.FreeTierOnly":
            friendly = "百炼 API 免费额度已耗尽。请在百炼控制台关闭“仅使用免费额度”模式，或充值后重试。"
            error_code = "BAILIAN_QUOTA_EXCEEDED"
        elif code.startswith("Throttling.") or response.status_code == 429:
            friendly = "百炼 API 请求过于频繁（限流），请稍后重试。"
            error_code = "BAILIAN_RATE_LIMITED"
        elif response.status_code in (401, 403):
            friendly = f"百炼 API 鉴权失败（HTTP {response.status_code}）：{message or '请检查 API Key 与业务空间配置。'}"
            error_code = "BAILIAN_AUTH_ERROR"
        elif code == "InvalidParameter" and "model" in lowered:
            friendly = f"模型不可用：{message}"
            error_code = "BAILIAN_MODEL_NOT_FOUND"
        else:
            friendly = f"百炼 API 调用失败（HTTP {response.status_code}，{code or 'UNKNOWN'}）：{message or '未知错误'}"
            error_code = "BAILIAN_HTTP_ERROR"
        raise BailianAPIException(
            friendly,
            error_code=error_code,
            status_code=response.status_code,
            details={"code": code, "message": message},
        )

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        seed: Optional[int] = None
    ):
        """
        初始化客户端

        Args:
            api_key: API Key，默认从配置读取
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成token数
            seed: 随机种子；默认使用配置值，固定后可降低重复请求的差异
        """
        self.api_key = api_key or settings.api.get_bailian_api_key()
        self.model = model or settings.api.bailian_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.seed = settings.api.bailian_seed if seed is None else seed
        self.last_usage: Optional[dict] = None

        if not self.api_key:
            raise ValueError("API Key未设置")

        logger.debug(f"BailianLLMClient初始化完成，模型: {self.model}")

    def _post(self, **kwargs) -> requests.Response:
        """发送请求；系统代理为本机且失效时自动直连重试。"""
        timeout = kwargs.pop('timeout', 120)
        try:
            return requests.post(self.base_url, timeout=timeout, **kwargs)
        except requests.exceptions.ProxyError:
            if not should_fallback_to_direct(self.base_url, settings.api.proxy_mode):
                raise
            host = urllib.parse.urlparse(self.base_url).hostname or ''
            logger.warning(f'系统代理不可用，DashScope 请求改用直连重试: {host}')
            with bypass_proxy_for([host]):
                return requests.post(self.base_url, timeout=timeout, **kwargs)

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        on_chunk: Optional[Callable[[str], None]] = None,
        seed: Optional[int] = None
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
            seed: 随机种子（覆盖默认值）

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
        
        # 不能用 `or`：temperature=0.0 是合法值，会被误替换成默认温度。
        effective_temperature = self.temperature if temperature is None else temperature
        effective_max_tokens = self.max_tokens if max_tokens is None else max_tokens
        effective_seed = self.seed if seed is None else seed

        payload = {
            "model": self.model,
            "input": {
                "messages": messages
            },
            "parameters": {
                "temperature": effective_temperature,
                "result_format": "message"
            }
        }

        if effective_max_tokens:
            payload["parameters"]["max_tokens"] = effective_max_tokens
        if effective_seed is not None:
            payload["parameters"]["seed"] = effective_seed

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        self.last_usage = None
        try:
            if stream and on_chunk:
                return self._stream_generate(payload, headers, on_chunk)
            else:
                response = self._post(
                    json=payload,
                    headers=headers,
                    timeout=120
                )
                self._raise_for_http_error(response)

                data = response.json()
                self.last_usage = data.get('usage')
                if self.last_usage:
                    logger.debug(f"LLM usage: {self.last_usage}")

                if "output" in data and "choices" in data["output"]:
                    return data["output"]["choices"][0]["message"]["content"]
                logger.error(f"Unexpected response format: {data}")
                raise BailianAPIException(
                    "百炼 API 返回格式异常，请稍后重试。",
                    error_code="BAILIAN_INVALID_RESPONSE",
                    details={"response": str(data)[:500]},
                )

        except BailianAPIException:
            raise
        except requests.exceptions.ProxyError as e:
            logger.error(f"代理连接失败: {e}")
            raise BailianAPIException(
                f"无法通过代理访问百炼 API：{e}。请检查代理/VPN 是否运行，"
                "或在设置中关闭“使用系统代理”。",
                error_code="BAILIAN_PROXY_ERROR",
            ) from e
        except requests.exceptions.RequestException as e:
            logger.error(f"API请求失败: {e}")
            raise BailianAPIException(
                f"无法连接百炼 API：{e}",
                error_code="BAILIAN_NETWORK_ERROR",
            ) from e
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
        self.last_usage = None

        try:
            response = self._post(
                json=payload,
                headers=headers,
                stream=True,
                timeout=120
            )
            self._raise_for_http_error(response)

            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data:'):
                        data_str = line[5:].strip()
                        if data_str == '[DONE]':
                            break
                        try:
                            data = json.loads(data_str)
                            usage = data.get('usage')
                            if usage:
                                self.last_usage = usage
                                logger.debug(f"LLM usage: {usage}")
                            if "output" in data and "choices" in data["output"]:
                                delta = data["output"]["choices"][0].get("message", {}).get("content", "")
                                if delta:
                                    on_chunk(delta)
                                    full_text.append(delta)
                        except json.JSONDecodeError:
                            continue
            
            return ''.join(full_text)
            
        except BailianAPIException:
            raise
        except requests.exceptions.ProxyError as e:
            logger.error(f"流式请求代理连接失败: {e}")
            raise BailianAPIException(
                f"无法通过代理访问百炼 API：{e}。请检查代理/VPN 是否运行，"
                "或在设置中关闭“使用系统代理”。",
                error_code="BAILIAN_PROXY_ERROR",
            ) from e
        except requests.exceptions.RequestException as e:
            logger.error(f"流式生成请求失败: {e}")
            raise BailianAPIException(
                f"无法连接百炼 API：{e}",
                error_code="BAILIAN_NETWORK_ERROR",
            ) from e
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


_SENTENCE_ENDINGS = frozenset('。！？!?…')
_SENTENCE_CLOSERS = frozenset("”’\"'」』）)】]》〉")
_SENTENCE_CHUNK_CHARS = 6000

# 修改分段提示词或重建规则时必须递增，避免复用旧的分析结果。
PARAGRAPH_PROMPT_VERSION = 'paragraph-breaks-v2'

GROUP_SYSTEM_PROMPT_ZH = """你是一个文本分段助手。用户会给出一个 JSON 句子数组，句子按顺序编号（第 1 个句子编号为 1）。
你的唯一任务是找出哪些句子需要开始一个新段落。

【输出要求】
- 只输出一个 JSON 对象，格式为 {"breaks": [3, 8, 15]}
- breaks 中的数字表示“新段落从第几个句子开始”，编号从 1 开始
- 第一个段落不需要在 breaks 中写 1
- 数字必须递增，且必须在 2..N 之间（N 是句子总数）
- 如果不需要分段，输出 {"breaks": []}
- 不允许输出原文、解释、Markdown 代码块或任何其他文字

示例：
输入：["你好。","今天天气不错。","我们出去走走吧。","好。"]
输出：{"breaks":[3]}"""

GROUP_SYSTEM_PROMPT_EN = """You are a paragraph segmentation assistant. The user provides a JSON array of sentences in order (the first sentence is 1).
Your only task is to decide which sentences start a new paragraph.

Output requirements:
- Output only a JSON object: {"breaks": [3, 8, 15]}
- Numbers in breaks are 1-based sentence indices where a new paragraph starts
- Do not include 1 (the first paragraph starts at the first sentence)
- Numbers must be increasing and within 2..N (N is the total sentence count)
- If no paragraph break is needed, output {"breaks": []}
- Do not output the original text, explanations, Markdown fences, or any other text

Example:
Input: ["Hello.","How are you?","Fine.","Thanks."]
Output: {"breaks":[3]}"""


def split_sentences(text: str) -> list[str]:
    """按句末标点切分句子，保证拼接后与原文逐字一致。"""
    if not text:
        return []
    sentences: list[str] = []
    start = 0
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        boundary = char in _SENTENCE_ENDINGS
        if char == '.':
            next_char = text[index + 1] if index + 1 < length else ''
            boundary = next_char == '' or next_char.isspace() or next_char in '.!?'
        if not boundary:
            index += 1
            continue
        end = index + 1
        while end < length and (
            text[end] in _SENTENCE_ENDINGS
            or text[end] in _SENTENCE_CLOSERS
            or text[end] == '.'
        ):
            end += 1
        sentences.append(text[start:end])
        start = end
        index = end
    if start < length:
        sentences.append(text[start:])
    return sentences


def _chunk_sentences(sentences: list[str], max_chars: int = _SENTENCE_CHUNK_CHARS) -> list[list[str]]:
    """把句子按字符预算分组，避免单次请求过长。"""
    chunks: list[list[str]] = []
    current: list[str] = []
    current_length = 0
    for sentence in sentences:
        if current and current_length + len(sentence) > max_chars:
            chunks.append(current)
            current = []
            current_length = 0
        current.append(sentence)
        current_length += len(sentence)
    if current:
        chunks.append(current)
    return chunks


def _build_group_prompt(sentences: list[str], language: str, retry_note: str = '') -> str:
    """构造分段请求；句子 JSON 固定放在最后一行，便于解析。"""
    payload = json.dumps(sentences, ensure_ascii=False)
    count = len(sentences)
    if language.startswith('en'):
        instruction = (
            'Decide which sentences start a new paragraph.\n'
            f'Total sentences N = {count}. Numbers in breaks must be increasing and within 2..{count}.\n'
            'Usually a paragraph contains multiple sentences; do not split every sentence '
            'and do not output too many breaks.\n'
            'If no break is needed, output {"breaks": []}.'
        )
    else:
        instruction = (
            '请判断以下句子中哪些需要开始新段落。\n'
            f'句子总数 N = {count}。breaks 中的数字必须递增，并且必须在 2..{count} 之间。\n'
            '通常每个段落包含多个句子；不要把每个句子单独分段，也不要输出过多边界。\n'
            '如果不需要分段，输出 {"breaks": []}。'
        )
    parts = [instruction]
    if retry_note:
        parts.append(retry_note)
    parts.append(payload)
    return '\n'.join(parts)


def _parse_paragraph_breaks(response: str, sentence_count: int) -> list[int]:
    """解析并校验段落起始句编号；容忍截断和少量越界编号。"""
    raw = (response or '').strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```[a-zA-Z]*\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

    numbers: Optional[list[int]] = None
    object_match = re.search(r'\{[\s\S]*\}', raw)
    array_match = re.search(r'\[[\s\S]*\]', raw)
    candidate = object_match.group() if object_match else (array_match.group() if array_match else '')
    if candidate:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            data = None
        if data is not None:
            if isinstance(data, dict):
                breaks = data.get('breaks')
                if breaks is None:
                    breaks = data.get('paragraph_starts')
            else:
                breaks = data
            if not isinstance(breaks, list):
                raise ValueError('AI 分段响应格式无效')
            numbers = []
            for value in breaks:
                if isinstance(value, bool):
                    raise ValueError('AI 分段响应包含无效编号')
                try:
                    numbers.append(int(value))
                except (TypeError, ValueError) as exc:
                    raise ValueError('AI 分段响应包含非数字编号') from exc

    if numbers is None:
        # 响应被 max_tokens 截断时，尽量从 breaks 数组或裸数组中抢救数字。
        break_match = re.search(r'"breaks"\s*:\s*\[([^\]]*)', raw)
        if break_match:
            numbers = [int(value) for value in re.findall(r'\d+', break_match.group(1))]
        elif '[' in raw:
            numbers = [int(value) for value in re.findall(r'\d+', raw[raw.find('[') + 1:])]
        else:
            raise ValueError('AI 分段响应缺少 JSON')

    valid = sorted({number for number in numbers if 2 <= number <= sentence_count})
    if numbers and not valid:
        raise ValueError('AI 分段响应的段落起始编号全部超出范围')
    return valid


def _request_paragraph_breaks(
    client: BailianLLMClient,
    sentences: list[str],
    system_prompt: str,
    language: str,
) -> list[int]:
    """请求段落起始编号，格式无效时重试一次。"""
    last_error: Optional[Exception] = None
    count = len(sentences)
    for attempt in range(2):
        retry_note = ''
        if attempt:
            retry_note = (
                f'The previous output was invalid: {last_error}. Output only valid JSON with a '
                f'"breaks" array; numbers must be between 2 and {count}.'
                if language.startswith('en') else
                f'上一次输出无效：{last_error}。请只输出合法 JSON 的 breaks 数组，编号必须在 2..{count} 之间。'
            )
        prompt = _build_group_prompt(sentences, language, retry_note)
        response = client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=min(2048, max(512, count * 4)),
        )
        if settings.api.log_llm_raw:
            logger.debug(f'AI 分段原始响应: {str(response)[:4000]}')
        try:
            return _parse_paragraph_breaks(response, count)
        except ValueError as exc:
            last_error = exc
            logger.warning(
                f'AI 分段响应无效（第 {attempt + 1} 次）: {exc}; '
                f'原始响应: {preview_llm_content(str(response), 200)}'
            )
    raise ValueError('AI 分段返回的段落起始编号无效，已放弃该结果') from last_error


def reorganize_paragraphs(text: str, language: str = "zh", context=None) -> str:
    """
    使用LLM整理文本段落

    模型只返回段落分组编号，原文句子由本地重建，
    从根本上避免模型改写、增删原文内容。

    Args:
        text: 原始清洗后的文本
        language: 文本语言 (zh=中文, en=英文 等)，用于选择对应提示词

    Returns:
        整理后的分段文本（段落间用空行分隔）
    """
    if not text or not text.strip():
        return text

    sentences = split_sentences(text)
    if not sentences:
        return text

    client = BailianLLMClient()
    system_prompt = GROUP_SYSTEM_PROMPT_EN if language.startswith('en') else GROUP_SYSTEM_PROMPT_ZH
    chunks = _chunk_sentences(sentences)
    results: list[str] = []
    for index, chunk in enumerate(chunks):
        if context:
            context.report(f'正在进行 AI 语义分段：第 {index + 1}/{len(chunks)} 块')
        breaks = _request_paragraph_breaks(client, chunk, system_prompt, language)
        if context:
            context.check()
        boundaries = [0] + [number - 1 for number in breaks] + [len(chunk)]
        paragraph_texts = [
            ''.join(chunk[boundaries[i]:boundaries[i + 1]])
            for i in range(len(boundaries) - 1)
        ]
        results.append('\n\n'.join(
            paragraph.strip() for paragraph in paragraph_texts if paragraph.strip()
        ))
    return '\n\n'.join(results)


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
