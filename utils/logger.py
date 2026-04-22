"""
日志工具模块

基于loguru的日志封装，提供统一的日志记录功能。
支持控制台输出和文件滚动日志。
"""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger


class LoggerConfig:
    """日志配置类"""
    
    def __init__(
        self,
        log_dir: str = "./logs",
        log_level: str = "INFO",
        console_output: bool = True,
        file_output: bool = True,
        rotation: str = "10 MB",
        retention: str = "7 days"
    ):
        self.log_dir = Path(log_dir)
        self.log_level = log_level.upper()
        self.console_output = console_output
        self.file_output = file_output
        self.rotation = rotation
        self.retention = retention
        
    def setup(self) -> None:
        """配置并初始化日志系统"""
        # 移除默认处理器
        logger.remove()
        
        # 格式化模板
        console_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        )
        
        file_format = (
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} - "
            "{message}"
        )
        
        # 添加控制台输出
        # PyInstaller console=False 模式下 stdout 可能为 None，需要检查
        if self.console_output and sys.stdout is not None:
            logger.add(
                sys.stdout,
                level=self.log_level,
                format=console_format,
                colorize=True,
                enqueue=True
            )
        
        # 添加文件输出
        if self.file_output:
            # 确保日志目录存在
            self.log_dir.mkdir(parents=True, exist_ok=True)
            
            # 主日志文件
            log_file = self.log_dir / "app.log"
            logger.add(
                log_file,
                level=self.log_level,
                format=file_format,
                rotation=self.rotation,
                retention=self.retention,
                encoding="utf-8",
                enqueue=True
            )
            
            # 错误日志单独记录
            error_log_file = self.log_dir / "error.log"
            logger.add(
                error_log_file,
                level="ERROR",
                format=file_format,
                rotation=self.rotation,
                retention=self.retention,
                encoding="utf-8",
                enqueue=True,
                filter=lambda record: record["level"].no >= 40  # ERROR级别为40
            )


def init_logger(
    log_dir: str = "./logs",
    log_level: str = "INFO",
    **kwargs
) -> None:
    """
    快速初始化日志系统
    
    Args:
        log_dir: 日志文件保存目录
        log_level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        **kwargs: 其他配置参数
    """
    config = LoggerConfig(
        log_dir=log_dir,
        log_level=log_level,
        **kwargs
    )
    config.setup()
    logger.info("日志系统初始化完成")


# 导出logger实例和配置函数
__all__ = ["logger", "init_logger", "LoggerConfig"]


# 如果直接运行此文件，进行测试
if __name__ == "__main__":
    # 初始化日志
    init_logger(log_level="DEBUG")
    
    # 测试各级别日志
    logger.debug("这是一条调试日志")
    logger.info("这是一条信息日志")
    logger.success("这是一条成功日志")
    logger.warning("这是一条警告日志")
    logger.error("这是一条错误日志")
    
    # 测试异常记录
    try:
        1 / 0
    except Exception as e:
        logger.exception(f"捕获到异常: {e}")
    
    print("\n日志测试完成，请检查 ./logs 目录下的日志文件")
