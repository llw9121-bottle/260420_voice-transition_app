"""
异常处理模块

定义应用中使用的自定义异常类，提供统一的异常处理机制。
"""

from typing import Any, Dict, Optional


class AppException(Exception):
    """
    应用基础异常类
    
    所有自定义异常的基类，提供统一的异常信息结构。
    """
    
    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
    
    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，便于序列化"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details
        }


# ==================== API相关异常 ====================

class APIException(AppException):
    """API调用异常基类"""
    pass


class DashScopeAPIException(APIException):
    """
    DashScope API 调用异常
    
    实时语音识别服务调用失败时抛出。
    """
    
    def __init__(
        self,
        message: str,
        error_code: str = "DASHSCOPE_ERROR",
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, error_code, details)
        self.status_code = status_code


class BailianAPIException(APIException):
    """
    阿里云百炼 API 调用异常
    
    大模型格式化服务调用失败时抛出。
    """
    
    def __init__(
        self,
        message: str,
        error_code: str = "BAILIAN_ERROR",
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, error_code, details)
        self.status_code = status_code


# ==================== 音频相关异常 ====================

class AudioException(AppException):
    """音频处理异常基类"""
    pass


class AudioDeviceException(AudioException):
    """
    音频设备异常
    
    麦克风设备无法访问或初始化失败时抛出。
    """
    
    def __init__(
        self,
        message: str = "无法访问麦克风设备",
        device_index: Optional[int] = None
    ):
        details = {}
        if device_index is not None:
            details["device_index"] = device_index
        super().__init__(message, "AUDIO_DEVICE_ERROR", details)


class AudioStreamException(AudioException):
    """
    音频流异常
    
    音频流读取或写入失败时抛出。
    """
    
    def __init__(self, message: str = "音频流操作失败"):
        super().__init__(message, "AUDIO_STREAM_ERROR")


# ==================== 文档相关异常 ====================

class DocumentException(AppException):
    """文档处理异常基类"""
    pass


class DocumentGenerationException(DocumentException):
    """
    文档生成异常
    
    Word文档生成失败时抛出。
    """
    
    def __init__(
        self,
        message: str = "文档生成失败",
        file_path: Optional[str] = None
    ):
        details = {}
        if file_path:
            details["file_path"] = file_path
        super().__init__(message, "DOCUMENT_GENERATION_ERROR", details)


class DocumentSaveException(DocumentException):
    """
    文档保存异常
    
    文档保存到磁盘失败时抛出。
    """
    
    def __init__(
        self,
        message: str = "文档保存失败",
        file_path: Optional[str] = None,
        reason: Optional[str] = None
    ):
        details = {}
        if file_path:
            details["file_path"] = file_path
        if reason:
            details["reason"] = reason
        super().__init__(message, "DOCUMENT_SAVE_ERROR", details)


# ==================== 配置相关异常 ====================

class ConfigException(AppException):
    """配置异常基类"""
    pass


class ConfigNotFoundException(ConfigException):
    """
    配置文件不存在异常
    """
    
    def __init__(self, config_path: str):
        super().__init__(
            f"配置文件不存在: {config_path}",
            "CONFIG_NOT_FOUND",
            {"config_path": config_path}
        )


class ConfigValidationException(ConfigException):
    """
    配置验证失败异常
    """
    
    def __init__(self, message: str, field: Optional[str] = None):
        details = {}
        if field:
            details["field"] = field
        super().__init__(message, "CONFIG_VALIDATION_ERROR", details)


# ==================== 异常处理工具函数 ====================

def handle_exception(
    exception: Exception,
    log_error: bool = True,
    re_raise: bool = False
) -> Optional[AppException]:
    """
    统一异常处理函数
    
    Args:
        exception: 捕获的异常
        log_error: 是否记录错误日志
        re_raise: 是否重新抛出异常
        
    Returns:
        转换后的AppException，如果不是AppException则返回None
    """
    from utils.logger import logger
    
    # 如果已经是AppException，直接处理
    if isinstance(exception, AppException):
        app_exception = exception
    else:
        # 转换为通用AppException
        app_exception = AppException(
            message=str(exception),
            error_code="UNKNOWN_ERROR",
            details={"original_type": type(exception).__name__}
        )
    
    # 记录日志
    if log_error:
        logger.error(f"[{app_exception.error_code}] {app_exception.message}")
        if app_exception.details:
            logger.debug(f"异常详情: {app_exception.details}")
    
    # 重新抛出
    if re_raise:
        raise app_exception
    
    return app_exception


def safe_execute(
    func,
    *args,
    default_return=None,
    error_message: str = "操作执行失败",
    **kwargs
):
    """
    安全执行函数，自动捕获异常
    
    Args:
        func: 要执行的函数
        args: 位置参数
        default_return: 异常时的默认返回值
        error_message: 错误提示信息
        kwargs: 关键字参数
        
    Returns:
        函数执行结果或默认值
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        handle_exception(
            AppException(
                message=f"{error_message}: {str(e)}",
                error_code="SAFE_EXECUTE_ERROR"
            ),
            log_error=True,
            re_raise=False
        )
        return default_return
