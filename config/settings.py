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
