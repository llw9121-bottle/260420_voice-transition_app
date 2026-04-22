"""
关键行为匹配功能演示脚本

演示如何使用 BehaviorMatcher 识别转录文本中的关键行为。
支持用户自定义4-7个关键行为条目，通过LLM进行智能匹配。

使用示例:
    python demo_behavior_matcher.py
"""

import sys
from typing import List

from loguru import logger

from core.formatter.behavior_matcher import (
    BehaviorConfig,
    BehaviorDefinition,
    BehaviorMatcher
)


def print_section(title: str):
    """打印章节标题"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60 + "\n")


def create_demo_config() -> BehaviorConfig:
    """创建演示用的行为配置（5个行为条目）"""
    
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
    ]
    
    return BehaviorConfig(
        behaviors=behaviors,
        min_confidence=0.6,
        include_context=True,
        context_chars=30
    )


def demo_basic_matching():
    """演示基础行为匹配"""
    print_section("演示 1: 基础行为匹配")
    
    # 示例转录文本
    text = """
    我经常和别人推荐这个产品，真的很好用。
    你确定要买这个吗？我觉得你应该再考虑一下。
    太好了，我们终于解决了这个问题！
    你知道吗，我听说他们要涨价了。
    我决定明天就动手做这个方案。
    """
    
    print("【输入文本】")
    print(text.strip())
    print()
    
    # 创建配置
    config = create_demo_config()
    
    print("【配置的行为条目】")
    for i, behavior in enumerate(config.behaviors, 1):
        print(f"  {i}. {behavior.name} - {behavior.description}")
    print()
    
    # 创建匹配器并执行匹配
    print("【正在执行行为匹配...】")
    try:
        matcher = BehaviorMatcher(config)
        matches = matcher.match(text)
        
        print(f"\n【匹配结果】共识别到 {len(matches)} 个行为\n")
        
        for i, match in enumerate(matches, 1):
            print(f"--- 匹配 #{i} ---")
            print(f"  行为名称: {match.behavior_name}")
            print(f"  置信度: {match.confidence:.1%}")
            print(f"  原文引用: \"{match.original_text}\"")
            print()
        
    except Exception as e:
        logger.error(f"行为匹配失败: {e}")
        print(f"错误: {e}")


def demo_custom_config():
    """演示自定义配置"""
    print_section("演示 2: 自定义行为配置")
    
    # 创建自定义配置（4个行为条目）
    custom_behaviors = [
        BehaviorDefinition(
            name="提问",
            description="提出问题或疑问",
            examples=["为什么", "怎么样", "这是什么"]
        ),
        BehaviorDefinition(
            name="同意",
            description="表示同意或认可",
            examples=["好的", "没问题", "我同意", "对的"]
        ),
        BehaviorDefinition(
            name="反对",
            description="表示不同意或反对",
            examples=["不行", "我不同意", "这样不好", "不对"]
        ),
        BehaviorDefinition(
            name="建议",
            description="提出建议或方案",
            examples=["我觉得可以", "建议这样做", "不如试试"]
        ),
    ]
    
    custom_config = BehaviorConfig(
        behaviors=custom_behaviors,
        min_confidence=0.7,  # 更高的置信度要求
        include_context=True,
        context_chars=20
    )
    
    # 测试文本
    test_text = """
    这个方案我觉得可以，建议我们就这样做。
    但是有人反对吗？如果有人不同意，可以提出来。
    好的，那就这么定了。
    """
    
    print("【自定义配置】")
    print(f"  行为条目数: {len(custom_config.behaviors)}")
    print(f"  最小置信度: {custom_config.min_confidence}")
    print(f"  行为列表: {[b.name for b in custom_config.behaviors]}")
    print()
    
    print("【测试文本】")
    print(test_text.strip())
    print()
    
    try:
        matcher = BehaviorMatcher(custom_config)
        matches = matcher.match(test_text)
        
        print(f"【匹配结果】识别到 {len(matches)} 个行为\n")
        
        for match in matches:
            print(f"  • {match.behavior_name} (置信度: {match.confidence:.0%})")
            print(f"    原文: \"{match.original_text}\"")
            print()
        
    except Exception as e:
        print(f"错误: {e}")


def main():
    """主函数"""
    print("="*60)
    print("  关键行为匹配功能演示")
    print("="*60)
    print()
    print("本演示展示如何使用 BehaviorMatcher 识别转录文本中的")
    print("关键行为。支持用户自定义 4-7 个行为条目，通过 LLM")
    print("进行智能匹配。")
    print()
    
    # 运行演示
    demo_basic_matching()
    demo_custom_config()
    
    print_section("演示完成")
    print()
    print("提示：")
    print("  • 在 GUI 中，用户可以通过表格界面配置行为条目")
    print("  • 每个行为包括：名称、描述、示例（可选）")
    print("  • 支持 4-7 个行为条目，置信度阈值可配置")
    print()


if __name__ == "__main__":
    main()
