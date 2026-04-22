"""
文件名策略模块

提供文档命名策略：时间戳命名、自定义模板。
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger


@dataclass
class NamingTemplate:
    """命名模板"""
    name: str                           # 模板名称
    template: str                       # 模板字符串
    description: str = ""               # 描述
    
    def validate(self) -> tuple[bool, str]:
        """验证模板有效性"""
        try:
            # 尝试解析模板
            self._extract_tokens()
            return True, "模板有效"
        except Exception as e:
            return False, f"模板无效: {e}"
    
    def _extract_tokens(self) -> List[str]:
        """提取模板中的变量"""
        pattern = r'\{([^}:]+)(?::([^}]+))?\}'
        return re.findall(pattern, self.template)


class NamingStrategy:
    """
    命名策略
    
    根据模板和上下文生成文件名。
    """
    
    # 默认模板
    DEFAULT_TEMPLATES: Dict[str, NamingTemplate] = {
        "timestamp": NamingTemplate(
            name="timestamp",
            template="{timestamp}",
            description="纯时间戳命名"
        ),
        "timestamp_title": NamingTemplate(
            name="timestamp_title",
            template="{timestamp}_{title}",
            description="时间戳+标题"
        ),
        "date_title": NamingTemplate(
            name="date_title",
            template="{date}_{title}",
            description="日期+标题"
        ),
        "session": NamingTemplate(
            name="session",
            template="{timestamp}_{session_id}",
            description="时间戳+会话ID"
        ),
    }
    
    def __init__(self, template: Optional[str] = None):
        """
        初始化命名策略
        
        Args:
            template: 模板名称或模板字符串，默认使用"timestamp"
        """
        self.template_str = template or "timestamp"
        self.custom_templates: Dict[str, NamingTemplate] = {}
    
    def add_template(self, template: NamingTemplate) -> None:
        """添加自定义模板"""
        is_valid, msg = template.validate()
        if not is_valid:
            raise ValueError(f"无效模板: {msg}")
        
        self.custom_templates[template.name] = template
        logger.info(f"添加自定义模板: {template.name}")
    
    def generate(
        self,
        title: str = "",
        session_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        extra_vars: Optional[Dict[str, str]] = None
    ) -> str:
        """
        生成文件名
        
        Args:
            title: 文档标题
            session_id: 会话ID
            timestamp: 时间戳（默认使用当前时间）
            extra_vars: 额外变量
            
        Returns:
            生成的文件名（不含扩展名）
        """
        ts = timestamp or datetime.now()
        
        # 构建变量字典
        variables = {
            "timestamp": ts.strftime("%Y%m%d_%H%M%S"),
            "date": ts.strftime("%Y%m%d"),
            "time": ts.strftime("%H%M%S"),
            "year": str(ts.year),
            "month": f"{ts.month:02d}",
            "day": f"{ts.day:02d}",
            "title": self._sanitize_filename(title) if title else "未命名",
            "session_id": session_id or "nosession",
        }
        
        # 添加额外变量
        if extra_vars:
            variables.update(extra_vars)
        
        # 获取模板
        template = self._get_template()
        
        # 替换变量
        try:
            result = template.template.format(**variables)
        except KeyError as e:
            logger.warning(f"模板变量缺失: {e}，使用默认模板")
            result = f"{variables['timestamp']}"
        
        # 清理文件名
        result = self._sanitize_filename(result)
        
        logger.info(f"生成文件名: {result}")
        return result
    
    def _get_template(self) -> NamingTemplate:
        """获取模板"""
        # 首先检查自定义模板
        if self.template_str in self.custom_templates:
            return self.custom_templates[self.template_str]
        
        # 检查默认模板
        if self.template_str in self.DEFAULT_TEMPLATES:
            return self.DEFAULT_TEMPLATES[self.template_str]
        
        # 尝试作为自定义模板字符串
        custom = NamingTemplate(
            name="custom",
            template=self.template_str
        )
        is_valid, _ = custom.validate()
        if is_valid:
            return custom
        
        # 默认使用时间戳
        return self.DEFAULT_TEMPLATES["timestamp"]
    
    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """
        清理文件名，移除非法字符
        
        Args:
            name: 原始名称
            
        Returns:
            清理后的名称
        """
        # Windows非法字符: < > : " / \ | ? *
        # 以及控制字符 (0-31)
        illegal_chars = '<>:"/\\|?*'
        
        result = name
        for char in illegal_chars:
            result = result.replace(char, '_')
        
        # 移除控制字符
        result = ''.join(char for char in result if ord(char) >= 32)
        
        # 移除首尾空格和点
        result = result.strip('. ')
        
        # 限制长度
        if len(result) > 200:
            result = result[:200]
        
        # 确保不为空
        if not result:
            result = "unnamed"
        
        return result


# 便捷函数

def generate_filename(
    title: str = "",
    session_id: Optional[str] = None,
    template: str = "timestamp"
) -> str:
    """
    便捷函数：快速生成文件名
    
    Args:
        title: 文档标题
        session_id: 会话ID
        template: 模板名称
        
    Returns:
        文件名（不含扩展名）
    """
    strategy = NamingStrategy(template=template)
    return strategy.generate(title=title, session_id=session_id)
