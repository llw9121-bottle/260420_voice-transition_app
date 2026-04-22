"""
配置文件管理模块

加载环境变量和配置，为应用提供统一的配置访问接口。
支持从.env文件加载配置。
"""

import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.logger import logger

# 加载.env文件
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path, encoding="utf-8")


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
    
    dashscope_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/api/v1",
        description="DashScope基础URL",
        validation_alias="DASHSCOPE_BASE_URL"
    )
    
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
        "dashscope_key_preview": api.dashscope_api_key[:8] + "***" if api.dashscope_api_key else "未设置",
        "bailian_key_preview": api.bailian_api_key[:8] + "***" if api.bailian_api_key else "未设置(可使用DashScope Key)",
    }


def save_api_configuration(dashscope_api_key: str, bailian_api_key: str = "") -> bool:
    """
    保存API配置到 .env 文件

    Args:
        dashscope_api_key: DashScope API Key
        bailian_api_key: Bailian API Key (可选，留空表示使用DashScope Key)

    Returns:
        是否保存成功
    """
    try:
        env_path = Path(__file__).parent.parent / ".env"
        env_example_path = Path(__file__).parent.parent / ".env.example"

        # 如果.env不存在，从.example复制模板
        if not env_path.exists() and env_example_path.exists():
            with open(env_example_path, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            # 读取现有内容
            if env_path.exists():
                with open(env_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            else:
                content = ""

        # 更新或添加DASHSCOPE_API_KEY
        lines = content.splitlines()
        new_lines = []
        dashscope_found = False
        bailian_found = False

        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith('DASHSCOPE_API_KEY='):
                new_lines.append(f'DASHSCOPE_API_KEY={dashscope_api_key}')
                dashscope_found = True
            elif line_stripped.startswith('BAILIAN_API_KEY='):
                new_lines.append(f'BAILIAN_API_KEY={bailian_api_key}')
                bailian_found = True
            else:
                new_lines.append(line)

        # 如果没找到，添加到末尾
        if not dashscope_found:
            new_lines.append(f'DASHSCOPE_API_KEY={dashscope_api_key}')
        if not bailian_found:
            new_lines.append(f'BAILIAN_API_KEY={bailian_api_key}')

        # 确保其他必要配置存在
        if not any(line.strip().startswith('DASHSCOPE_REGION=') for line in new_lines):
            new_lines.append('DASHSCOPE_REGION=cn-beijing')
        if not any(line.strip().startswith('OUTPUT_DIR=') for line in new_lines):
            new_lines.append('OUTPUT_DIR=./output')

        # 写入文件
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines) + '\n')

        logger.info(f"API配置已保存到: {env_path}")
        return True

    except Exception as e:
        logger.error(f"保存API配置失败: {e}")
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
