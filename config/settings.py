"""
配置文件管理模块

加载环境变量和配置，为应用提供统一的配置访问接口。
支持从.env文件加载配置。
"""

import os
import re
import sys
import tempfile
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 计算项目根目录
# PyInstaller 打包后，需要从可执行文件位置推算项目根目录
if getattr(sys, 'frozen', False):
    if sys.platform == 'darwin':
        # .app/Contents/MacOS/App 的可执行文件位于 bundle 内部，
        # 数据目录放到 .app 同级，避免向只读 bundle 写入配置。
        try:
            project_root = Path(sys.executable).resolve().parents[2].parent
        except IndexError:
            project_root = Path(sys.executable).parent
    else:
        # Windows/Linux one-file：项目根目录即可执行文件所在目录。
        project_root = Path(sys.executable).parent
else:
    # 源码运行：从当前文件位置推算
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

from utils.logger import logger
from utils.proxy import apply_proxy_policy

# 加载.env文件：始终从项目根目录读取
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, encoding="utf-8")

# 公共域名按地域映射；未列出的地域回退到北京。
_PUBLIC_DASHSCOPE_HOSTS = {
    "cn-beijing": "dashscope.aliyuncs.com",
    "ap-southeast-1": "dashscope-intl.aliyuncs.com",
    "us-east-1": "dashscope-us.aliyuncs.com",
    "cn-hongkong": "cn-hongkong.dashscope.aliyuncs.com",
}


class APISettings(BaseSettings):
    """API配置"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # DashScope配置（实时语音识别）
    dashscope_api_key: str = Field(
        default="",
        description="DashScope API Key，用于实时语音识别",
        validation_alias="DASHSCOPE_API_KEY"
    )
    
    # 百炼配置（大模型格式化）
    bailian_api_key: str = Field(
        default="",
        description="阿里云百炼 API Key，用于大模型格式化",
        validation_alias="BAILIAN_API_KEY"
    )
    
    # 地域配置（可选）
    dashscope_region: str = Field(
        default="cn-beijing",
        description="DashScope服务地域",
        validation_alias="DASHSCOPE_REGION"
    )

    # 业务空间 ID（可选）。填写后使用专属域名，留空使用公共域名。
    dashscope_workspace_id: str = Field(
        default="",
        description="百炼业务空间 ID，形如 llm-xxxxxxxxxxxx",
        validation_alias="DASHSCOPE_WORKSPACE_ID"
    )

    # 显式覆盖地址（可选）。留空时按地域/业务空间自动推导。
    dashscope_base_url: str = Field(
        default="",
        description="DashScope HTTP 基础URL，需包含 /api/v1",
        validation_alias="DASHSCOPE_BASE_URL"
    )

    dashscope_ws_base_url: str = Field(
        default="",
        description="DashScope WebSocket 基础URL，需包含 /api-ws/v1/realtime",
        validation_alias="DASHSCOPE_WS_BASE_URL"
    )

    proxy_mode: str = Field(
        default="system",
        description="代理模式: system/direct/manual",
        validation_alias="DASHSCOPE_PROXY_MODE"
    )

    proxy_url: str = Field(
        default="",
        description="手动代理地址，如 http://127.0.0.1:7890",
        validation_alias="DASHSCOPE_PROXY_URL"
    )

    bailian_model: str = Field(
        default="qwen-plus",
        description="百炼文本生成模型",
        validation_alias="BAILIAN_MODEL"
    )

    # 固定种子不能保证逐字一致，但能明显降低同一输入的采样漂移。
    bailian_seed: int = Field(
        default=42,
        description="百炼文本生成随机种子；设置后同一请求更稳定",
        validation_alias="BAILIAN_SEED"
    )

    log_llm_raw: bool = Field(
        default=False,
        description="是否在日志中记录原始 LLM 响应/引文（默认脱敏）",
        validation_alias="LOG_LLM_RAW"
    )

    @property
    def dashscope_host(self) -> str:
        """按业务空间和地域推导服务域名。"""
        region = (self.dashscope_region or "cn-beijing").strip().lower()
        workspace = (self.dashscope_workspace_id or "").strip()
        if workspace:
            return f"{workspace}.{region}.maas.aliyuncs.com"
        return _PUBLIC_DASHSCOPE_HOSTS.get(region, _PUBLIC_DASHSCOPE_HOSTS["cn-beijing"])

    @property
    def http_base_url(self) -> str:
        """DashScope 原生 HTTP API 基础地址。"""
        override = (self.dashscope_base_url or "").strip()
        if override:
            return override.rstrip("/")
        return f"https://{self.dashscope_host}/api/v1"

    @property
    def ws_base_url(self) -> str:
        """实时语音识别 WebSocket 完整地址。"""
        override = (self.dashscope_ws_base_url or "").strip()
        if override:
            return override.rstrip("/")
        return f"wss://{self.dashscope_host}/api-ws/v1/realtime"

    @property
    def is_dashscope_configured(self) -> bool:
        """检查DashScope是否已配置"""
        return bool(self.dashscope_api_key and self.dashscope_api_key != "your_dashscope_api_key_here")
    
    @property
    def is_bailian_configured(self) -> bool:
        """检查百炼是否已配置"""
        # 如果BAILIAN_API_KEY未设置，可使用DASHSCOPE_API_KEY
        key = self.bailian_api_key or self.dashscope_api_key
        return bool(key and key != "your_bailian_api_key_here")
    
    def get_bailian_api_key(self) -> str:
        """获取有效的百炼API Key"""
        if self.bailian_api_key and self.bailian_api_key != "your_bailian_api_key_here":
            return self.bailian_api_key
        return self.dashscope_api_key


class AudioSettings(BaseSettings):
    """音频录制配置"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    sample_rate: int = Field(default=16000, description="采样率(Hz)")
    channels: int = Field(default=1, description="声道数")
    chunk_size: int = Field(default=1024, description="音频块大小")
    format: str = Field(default="int16", description="音频格式 (int16, float32)")


class DocumentSettings(BaseSettings):
    """文档生成配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    output_dir: str = Field(
        default="./output",
        description="文档输出目录",
        validation_alias="OUTPUT_DIR"
    )

    default_format_style: str = Field(
        default="standard",
        description="默认格式化风格(standard/formal/concise/meeting)",
        validation_alias="DEFAULT_FORMAT_STYLE"
    )


class ASRSettings(BaseSettings):
    """语音识别配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    language: str = Field(
        default="zh",
        description="识别语言 (zh=中文, yue=粤语, en=英文, ja=日语等)",
        validation_alias="ASR_LANGUAGE"
    )

    vad_enable: bool = Field(
        default=True,
        description="是否启用语音活动检测(VAD)",
        validation_alias="ASR_VAD_ENABLE"
    )

    vad_threshold: float = Field(
        default=0.0,
        description="VAD检测阈值 [-1, 1], 推荐 0.0",
        validation_alias="ASR_VAD_THRESHOLD"
    )

    vad_silence_ms: int = Field(
        default=400,
        description="VAD静音检测时长(ms) [200, 6000]",
        validation_alias="ASR_VAD_SILENCE_MS"
    )

    auto_reconnect: bool = Field(
        default=True,
        description="网络断开是否自动重连",
        validation_alias="ASR_AUTO_RECONNECT"
    )

    max_reconnect_attempts: int = Field(
        default=3,
        description="最大重连尝试次数",
        validation_alias="ASR_MAX_RECONNECT_ATTEMPTS"
    )

    log_asr_text: bool = Field(
        default=False,
        description="是否在日志中记录完整转写文本（默认脱敏）",
        validation_alias="LOG_ASR_TEXT"
    )


class AppSettings(BaseSettings):
    """应用全局配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    debug: bool = Field(default=False, description="调试模式")
    log_level: str = Field(default="INFO", description="日志级别")

    # 子配置
    api: APISettings = Field(default_factory=APISettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    document: DocumentSettings = Field(default_factory=DocumentSettings)
    asr: ASRSettings = Field(default_factory=ASRSettings)


# 全局配置实例
settings = AppSettings()

# 在进程启动早期应用代理策略，requests 与 websocket-client 都会读取这些环境变量。
apply_proxy_policy(
    settings.api.proxy_mode,
    settings.api.proxy_url,
    [
        'dashscope.aliyuncs.com',
        'dashscope-intl.aliyuncs.com',
        'dashscope-us.aliyuncs.com',
        'cn-hongkong.dashscope.aliyuncs.com',
        settings.api.dashscope_host,
    ],
)


def preview_llm_content(value: str, limit: int = 200) -> str:
    """日志中的 LLM 内容预览；默认脱敏，仅在 LOG_LLM_RAW=true 时输出原文。"""
    text = value or ''
    if settings.api.log_llm_raw:
        return text[:limit]
    return f'<redacted len={len(text)}>'


def preview_asr_content(value: str, limit: int = 120) -> str:
    """日志中的 ASR 文本预览；默认脱敏，仅在 LOG_ASR_TEXT=true 时输出原文。"""
    text = value or ''
    if settings.asr.log_asr_text:
        return text[:limit]
    return f'<redacted len={len(text)}>'


def check_api_configuration() -> dict:
    """
    检查API配置状态

    Returns:
        配置状态字典
    """
    api = settings.api

    return {
        "dashscope_configured": api.is_dashscope_configured,
        "bailian_configured": api.is_bailian_configured,
        "dashscope_key_preview": "已设置" if api.dashscope_api_key else "未设置",
        "bailian_key_preview": "已设置" if api.bailian_api_key else "未设置(可使用DashScope Key)",
    }


_ENV_API_KEY_PATTERN = re.compile(r'[A-Za-z0-9._-]+')
_ENV_REGION_PATTERN = re.compile(r'[a-z0-9-]{1,64}')
_ENV_WORKSPACE_PATTERN = re.compile(r'[A-Za-z0-9-]{0,128}')
_ENV_PROXY_MODES = frozenset({'system', 'direct', 'manual'})
_ENV_PROXY_SCHEMES = frozenset({'http', 'https', 'socks5', 'socks5h'})


def _sanitize_env_value(value: str, field: str, max_length: int = 512) -> str:
    """拒绝换行/空字符，防止写入 .env 时注入额外配置项。"""
    text = (value or '').strip()
    if len(text) > max_length:
        raise ValueError(f'{field}长度超过 {max_length} 个字符')
    if any(char in text for char in ('\n', '\r', '\x00')):
        raise ValueError(f'{field}包含非法控制字符')
    return text


def _validate_api_key(value: str, field: str, allow_empty: bool = True) -> str:
    text = _sanitize_env_value(value, field, 512)
    if not text:
        if allow_empty:
            return ''
        raise ValueError(f'{field}不能为空')
    if not _ENV_API_KEY_PATTERN.fullmatch(text):
        raise ValueError(f'{field}格式无效')
    return text


def _validate_region(value: str) -> str:
    text = _sanitize_env_value(value, '服务地域', 64) or 'cn-beijing'
    if not _ENV_REGION_PATTERN.fullmatch(text):
        raise ValueError('服务地域格式无效')
    return text


def _validate_workspace(value: str) -> str:
    text = _sanitize_env_value(value, '业务空间 ID', 128)
    if text and not _ENV_WORKSPACE_PATTERN.fullmatch(text):
        raise ValueError('业务空间 ID 格式无效')
    return text


def _validate_proxy_mode(value: str) -> str:
    text = _sanitize_env_value(value, '代理模式', 16) or 'system'
    if text not in _ENV_PROXY_MODES:
        raise ValueError('代理模式必须是 system/direct/manual')
    return text


def _validate_proxy_url(value: str) -> str:
    text = _sanitize_env_value(value, '代理地址', 512)
    if not text:
        return ''
    parsed = urlparse(text if '://' in text else f'http://{text}')
    if parsed.scheme.lower() not in _ENV_PROXY_SCHEMES or not parsed.hostname:
        raise ValueError('代理地址格式无效')
    return text


def _upsert_env_line(lines: List[str], key: str, value: str) -> None:
    """原地更新或追加 .env 配置项。"""
    text = _sanitize_env_value(value, key, 1024)
    prefix = f'{key}='
    for index, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[index] = f'{key}={text}'
            return
    lines.append(f'{key}={text}')


def _load_env_lines() -> List[str]:
    env_path = project_root / '.env'
    example_path = project_root / '.env.example'
    if env_path.exists():
        return env_path.read_text(encoding='utf-8').splitlines()
    if example_path.exists():
        return example_path.read_text(encoding='utf-8').splitlines()
    return []


def _write_env_file(lines: List[str]) -> Path:
    """原子写入 .env，失败时保留旧配置；尽可能收紧文件权限。"""
    env_path = project_root / '.env'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=project_root,
            prefix='.env-', suffix='.tmp', delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write('\n'.join(lines).rstrip('\n') + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, env_path)
        try:
            os.chmod(env_path, 0o600)
        except OSError:
            logger.debug('当前平台不支持收紧 .env 文件权限')
        return env_path
    finally:
        if temporary and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                logger.warning(f'无法清理临时配置文件: {temporary}')


def save_api_configuration(
    dashscope_api_key: str,
    bailian_api_key: str = "",
    region: Optional[str] = None,
    workspace_id: Optional[str] = None,
    proxy_mode: Optional[str] = None,
    proxy_url: Optional[str] = None,
) -> bool:
    """
    保存 API 配置到 .env 文件。

    Args:
        dashscope_api_key: DashScope API Key
        bailian_api_key: Bailian API Key（可选，留空表示使用 DashScope Key）
        region: 服务地域；None 表示保留原值
        workspace_id: 业务空间 ID；None 表示保留原值，空字符串表示清除
        proxy_mode: 代理模式 system/direct/manual；None 表示保留原值
        proxy_url: 手动代理地址；None 表示保留原值，空字符串表示清除

    Returns:
        是否保存成功
    """
    try:
        dashscope_key = _validate_api_key(dashscope_api_key, 'DashScope API Key', allow_empty=False)
        bailian_key = _validate_api_key(bailian_api_key, '百炼 API Key')
        lines = _load_env_lines()

        _upsert_env_line(lines, 'DASHSCOPE_API_KEY', dashscope_key)
        _upsert_env_line(lines, 'BAILIAN_API_KEY', bailian_key)
        if region is not None:
            _upsert_env_line(lines, 'DASHSCOPE_REGION', _validate_region(region))
        elif not any(line.strip().startswith('DASHSCOPE_REGION=') for line in lines):
            _upsert_env_line(lines, 'DASHSCOPE_REGION', 'cn-beijing')
        if workspace_id is not None:
            _upsert_env_line(lines, 'DASHSCOPE_WORKSPACE_ID', _validate_workspace(workspace_id))
        if proxy_mode is not None:
            _upsert_env_line(lines, 'DASHSCOPE_PROXY_MODE', _validate_proxy_mode(proxy_mode))
        if proxy_url is not None:
            _upsert_env_line(lines, 'DASHSCOPE_PROXY_URL', _validate_proxy_url(proxy_url))
        if not any(line.strip().startswith('OUTPUT_DIR=') for line in lines):
            _upsert_env_line(lines, 'OUTPUT_DIR', './output')

        env_path = _write_env_file(lines)
        logger.info(f"API 配置已保存: {env_path}")
        return True
    except Exception as e:
        logger.error(f"保存 API 配置失败: {e}")
        return False


def save_output_directory(output_dir: str) -> bool:
    """保存默认导出目录；拒绝换行等可破坏 .env 的输入。"""
    try:
        value = _sanitize_env_value(output_dir, '输出目录', 512)
        if not value:
            raise ValueError('输出目录不能为空')
        lines = _load_env_lines()
        _upsert_env_line(lines, 'OUTPUT_DIR', value)
        _write_env_file(lines)
        logger.info(f'默认输出目录已保存: {value}')
        return True
    except Exception as e:
        logger.error(f'保存默认输出目录失败: {e}')
        return False


if __name__ == "__main__":
    # 测试配置加载
    logger.info("=== 配置加载测试 ===")
    logger.info(f"调试模式: {settings.debug}")
    logger.info(f"日志级别: {settings.log_level}")

    logger.info("\n=== API配置 ===")
    status = check_api_configuration()
    for key, value in status.items():
        logger.info(f"{key}: {value}")

    logger.info("\n=== 音频配置 ===")
    logger.info(f"采样率: {settings.audio.sample_rate}Hz")
    logger.info(f"声道数: {settings.audio.channels}")

    logger.info("\n=== 文档配置 ===")
    logger.info(f"输出目录: {settings.document.output_dir}")
    logger.info(f"默认格式风格: {settings.document.default_format_style}")

    logger.info("\n=== ASR 识别配置 ===")
    logger.info(f"识别语言: {settings.asr.language}")
    logger.info(f"VAD启用: {settings.asr.vad_enable}")
    logger.info(f"VAD阈值: {settings.asr.vad_threshold}")
    logger.info(f"VAD静音时长: {settings.asr.vad_silence_ms}ms")
    logger.info(f"自动重连: {settings.asr.auto_reconnect}")
    logger.info(f"最大重连次数: {settings.asr.max_reconnect_attempts}")
