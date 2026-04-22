"""
pytest 配置文件

提供全局测试配置和fixture。
"""

import pytest
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(autouse=True)
def setup_test_env():
    """测试环境设置"""
    # 可以在这里设置全局测试环境变量
    yield
    # 测试后清理
