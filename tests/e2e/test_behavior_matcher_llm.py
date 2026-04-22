"""
行为匹配功能 LLM API 测试脚本

使用真实的百炼 API 测试关键行为匹配功能。
需要先配置 BAILIAN_API_KEY 环境变量或在 .env 文件中配置。

运行方式：
    python test_behavior_matcher_llm.py
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import settings
from core.formatter.behavior_matcher import (
    BehaviorConfig,
    BehaviorDefinition,
    BehaviorMatcher,
    BehaviorMatch
)


def print_header(title: str):
    """打印章节标题"""
    print("")
    print("=" * 70)
    print("  " + title)
    print("=" * 70)
    print("")


def print_separator():
    """打印分隔线"""
    print("")
    print("-" * 70)
    print("")


def check_api_configuration() -> bool:
    """检查 API 配置"""
    print_header("API 配置检查")
    
    bailian_key = settings.api.get_bailian_api_key()
    
    if not bailian_key:
        print("[X] 未配置百炼 API Key")
        print("    请在 .env 文件中设置 BAILIAN_API_KEY")
        return False
    
    print("[OK] 百炼 API Key 已配置: " + bailian_key[:8] + "...")
    print("     地域: " + settings.api.dashscope_region)
    
    return True


def create_test_config() -> BehaviorConfig:
    """创建测试用的行为配置（6个行为条目）"""
    
    behaviors = [
        BehaviorDefinition(
            name="说服影响",
            description="试图影响他人观点、决策或行为，包含推荐、劝说、引导等",
            examples=[
                "我经常和别人推荐这个东西",
                "你应该这样做",
                "相信我，这绝对是对的",
                "大家都在用，你也试试吧"
            ]
        ),
        BehaviorDefinition(
            name="质疑追问",
            description="对某事表示怀疑、不确定，或进一步追问细节",
            examples=[
                "真的吗",
                "那我要不要...",
                "你确定吗",
                "为什么这么说",
                "能详细说说吗"
            ]
        ),
        BehaviorDefinition(
            name="情绪表达",
            description="表达个人情绪状态，如高兴、焦虑、沮丧、兴奋等",
            examples=[
                "我觉得很开心",
                "太棒了",
                "我真的很担心",
                "有点郁闷",
                "太激动了"
            ]
        ),
        BehaviorDefinition(
            name="信息分享",
            description="主动分享信息、经验、知识或个人见解",
            examples=[
                "我听说...",
                "根据我的经验...",
                "有个消息要告诉你",
                "你知道吗",
                "我觉得应该让你知道"
            ]
        ),
        BehaviorDefinition(
            name="决策倾向",
            description="表达某种决策意向或行动倾向",
            examples=[
                "我决定...",
                "打算这样做",
                "我准备...",
                "我觉得应该...",
                "我会考虑的"
            ]
        ),
        BehaviorDefinition(
            name="寻求共识",
            description="试图寻找共同点或达成一致意见",
            examples=[
                "我们都同意...",
                "大家怎么看",
                "这样可以吗",
                "你觉得怎么样",
                "有没有其他意见"
            ]
        ),
    ]
    
    return BehaviorConfig(
        behaviors=behaviors,
        min_confidence=0.6,
        include_context=True,
        context_chars=30
    )


def test_basic_matching():
    """测试基础行为匹配"""
    print_header("测试 1: 基础行为匹配")
    
    # 测试文本 - 模拟会议讨论场景
    test_text = """
    产品经理：我们今天讨论一下下个季度的产品规划。
    
    开发A：我觉得我们可以优先做用户反馈最多的功能，大家都同意吗？
    
    产品经理：嗯，这个建议很好。大家觉得怎么样？有没有其他意见？
    
    开发B：我有点担心资源不够，真的可以同时做这么多功能吗？
    
    产品经理：你的担心有道理。我们可能需要调整一下优先级。
    
    开发A：太好了，终于达成一致了！我很开心能推进这个项目。
    """
    
    print("[输入文本]")
    print("  长度: " + str(len(test_text)) + " 字符")
    print("  预览: " + test_text[:100] + "...")
    print()
    
    # 创建配置
    config = create_test_config()
    
    print("[配置的行为条目](共" + str(len(config.behaviors)) + "个)")
    for i, behavior in enumerate(config.behaviors, 1):
        print("  " + str(i) + ". " + behavior.name + ": " + behavior.description[:40] + "...")
    print()
    
    # 执行匹配
    print("[正在调用 LLM API 进行行为匹配...]")
    print("  这可能需要几秒钟时间...")
    print()
    
    try:
        start_time = datetime.now()
        matcher = BehaviorMatcher(config)
        matches = matcher.match(test_text)
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print("[匹配完成]耗时: " + str(round(elapsed, 2)) + "秒")
        print("[匹配结果]共识别到 " + str(len(matches)) + " 个行为")
        print()
        
        if matches:
            for i, match in enumerate(matches, 1):
                print("--- 匹配 #" + str(i) + " ---")
                print("  行为名称: " + match.behavior_name)
                print("  置信度: " + str(round(match.confidence * 100, 1)) + "%")
                text = match.original_text[:60]
                if len(match.original_text) > 60:
                    text += "..."
                print("  原文引用: \"" + text + "\"")
                print("  位置: " + str(match.context_start) + "-" + str(match.context_end))
                print()
        else:
            print("  (未识别到匹配的行为)")
        
        return len(matches) > 0
        
    except Exception as e:
        print("[X] 行为匹配失败: " + str(e))
        import traceback
        traceback.print_exc()
        return False


def test_config_validation():
    """测试配置验证"""
    print_header("测试 2: 配置验证")
    
    from core.formatter.behavior_matcher import BehaviorConfig, BehaviorDefinition
    
    # 测试有效配置
    valid_config = BehaviorConfig(behaviors=[
        BehaviorDefinition(name="测试1", description="测试", examples=["例子"]),
        BehaviorDefinition(name="测试2", description="测试", examples=["例子"]),
    ])
    
    is_valid, msg = valid_config.validate()
    test_result = "[OK] 通过" if is_valid else "[X] 失败 (" + msg + ")"
    print("  有效配置验证: " + test_result)
    
    # 测试空配置
    empty_config = BehaviorConfig(behaviors=[])
    is_valid, msg = empty_config.validate()
    test_result = "[OK] 通过" if not is_valid else "[X] 失败 (应检测为空)"
    print("  空配置验证: " + test_result)
    
    # 测试重复名称
    dup_config = BehaviorConfig(behaviors=[
        BehaviorDefinition(name="相同名称", description="测试1"),
        BehaviorDefinition(name="相同名称", description="测试2"),
    ])
    is_valid, msg = dup_config.validate()
    test_result = "[OK] 通过" if not is_valid else "[X] 失败 (应检测重复)"
    print("  重复名称验证: " + test_result)


def test_naming_and_export():
    """测试文件名策略和导出功能"""
    print_header("测试 3: 文件名策略和导出")
    
    from core.formatter.base import FormattedDocument, FormattingStyle, BehaviorMatch
    from core.formatter.naming import NamingStrategy
    from core.formatter.exporters import JSONExporter, MarkdownExporter
    
    # 创建测试文档
    doc = FormattedDocument(
        title="测试文档",
        raw_text="测试内容",
        formatted_text="格式化后的内容",
        style=FormattingStyle.CLEANED,
        session_id="test_123",
        word_count=10,
        duration_seconds=60.0,
        behavior_matches=[
            BehaviorMatch(
                behavior_name="测试行为",
                original_text="测试",
                confidence=0.9,
                context_start=0,
                context_end=2
            )
        ]
    )
    
    # 测试文件名策略
    print("  [文件名策略测试]")
    strategy = NamingStrategy(template="timestamp_title")
    filename = strategy.generate(title="会议记录", session_id="sess_abc")
    print("    生成文件名: " + filename)
    result = "[OK] 通过" if len(filename) > 0 and "_" in filename else "[X] 失败"
    print("    验证: " + result)
    
    # 测试 JSON 导出
    print("\n  [JSON 导出测试]")
    try:
        output_dir = Path("./output/test_behavior")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        json_exporter = JSONExporter()
        json_path = json_exporter.export(doc, output_dir / "test_doc")
        
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                data = f.read()
            print("    导出成功: " + str(json_path))
            print("    文件大小: " + str(len(data)) + " 字节")
            print("    验证: [OK] 通过")
        else:
            print("    验证: [X] 失败 (文件不存在)")
    except Exception as e:
        print("    导出失败: " + str(e))
        print("    验证: [X] 失败")


def main():
    """主函数"""
    print("")
    print("=" * 70)
    print("  行为匹配功能 LLM API 测试")
    print("=" * 70)
    print("")
    print("本测试将：")
    print("  1. 检查 API 配置")
    print("  2. 测试配置验证功能")
    print("  3. 调用 LLM API 进行实际的行为匹配")
    print("  4. 测试文件名策略和导出功能")
    print("")
    
    # 检查 API 配置
    if not check_api_configuration():
        print("")
        print("[WARNING] API 配置检查失败，请检查 .env 文件配置")
        return 1
    
    # 运行测试
    try:
        test_config_validation()
        test_naming_and_export()
        
        # 主要测试：行为匹配
        success = test_basic_matching()
        
        # 总结
        print("")
        print("=" * 70)
        print("  测试完成")
        print("=" * 70)
        print("")
        
        if success:
            print("[OK] 行为匹配功能测试通过！")
        else:
            print("[WARNING] 行为匹配功能可能需要检查")
        
        print("")
        print("输出文件：")
        print("  - ./output/test_behavior/")
        print("")
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("")
        print("")
        print("[WARNING] 测试被用户中断")
        return 130
    except Exception as e:
        logger.error("测试执行失败: " + str(e))
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
