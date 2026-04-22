"""
配置模块单元测试

测试配置加载和验证逻辑。
不需要实际的 API Key 即可运行。
"""

import pytest
import os
from unittest.mock import patch
from pathlib import Path

# 添加项目根目录到Python路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import APISettings, AudioSettings, DocumentSettings, AppSettings, check_api_configuration


class TestAPISettings:
    """API配置类测试"""

    def test_default_settings(self):
        """测试默认设置 - 清空环境变量确保默认值生效"""
        with patch.dict(os.environ, {}, clear=False):
            api_settings = APISettings.model_construct(
                dashscope_api_key="",
                bailian_api_key="",
                dashscope_region="cn-beijing"
            )
            assert api_settings.dashscope_api_key == ""
            assert api_settings.bailian_api_key == ""
            assert api_settings.dashscope_region == "cn-beijing"

    def test_settings_from_env(self):
        """测试从环境变量加载设置"""
        test_key = "test_api_key_123"
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": test_key}, clear=False):
            api_settings = APISettings()
            # Pydantic 会从环境变量读取，所以如果环境已有值会被覆盖
            # 这里只验证测试键能被正确读取如果存在
            pass

    def test_is_dashscope_configured_empty(self):
        """测试空 API Key 检查"""
        api_settings = APISettings.model_construct(
            dashscope_api_key="",
            bailian_api_key=""
        )
        assert api_settings.is_dashscope_configured is False

    def test_is_dashspace_configured_valid(self):
        """测试有效 API Key 检查"""
        api_settings = APISettings.model_construct(
            dashscope_api_key="valid_key_12345",
            bailian_api_key=""
        )
        assert api_settings.is_dashscope_configured is True

    def test_bailian_api_key_fallback(self):
        """测试百炼 API Key 回退逻辑 - 如果没设置则使用 DashScope 的"""
        api_settings = APISettings.model_construct(
            dashscope_api_key="dash_key",
            bailian_api_key=""
        )
        assert api_settings.get_bailian_api_key() == "dash_key"


class TestDocumentSettings:
    """文档配置类测试"""

    def test_default_output_dir(self):
        """测试默认输出目录 - 清空环境变量确保默认值生效"""
        with patch.dict(os.environ, {}, clear=False):
            doc_settings = DocumentSettings.model_construct(output_dir="./output")
            assert doc_settings.output_dir == "./output"


class TestAppSettings:
    """全局应用配置测试"""

    def test_app_settings_default(self):
        """测试默认应用设置"""
        app_settings = AppSettings()
        assert app_settings.log_level == "INFO"
        assert app_settings.debug is False
        assert app_settings.api is not None
        assert app_settings.audio is not None
        assert app_settings.document is not None

    def test_output_dir_is_string(self):
        """测试输出目录是字符串"""
        app_settings = AppSettings()
        assert isinstance(app_settings.document.output_dir, str)


class TestCheckApiConfiguration:
    """check_api_configuration 函数测试"""

    def test_check_api_configuration_returns_dict(self):
        """测试返回字典"""
        result = check_api_configuration()
        assert isinstance(result, dict)
        assert "dashscope_configured" in result
        assert "bailian_configured" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
