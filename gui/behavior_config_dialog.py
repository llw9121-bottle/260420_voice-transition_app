"""
关键行为配置对话框

提供弹窗式表格界面，用于配置 4-7 个关键行为条目。
支持添加、删除、编辑行为定义。
支持导入/导出配置，提供常用场景预置模板。
"""

import json
import re
import sys
import customtkinter as ctk
from tkinter import messagebox
from tkinter import filedialog
from typing import List, Optional, Callable

from loguru import logger

from core.formatter.behavior_matcher import BehaviorDefinition, BehaviorConfig

# 默认字体：Windows 使用微软雅黑，其他平台使用系统默认
if sys.platform.startswith('win'):
    DEFAULT_FONT_FAMILY = "Microsoft YaHei"
else:
    # macOS/Linux 使用系统默认字体
    DEFAULT_FONT_FAMILY = None


class BehaviorConfigDialog:
    """
    行为配置对话框
    
    使用弹窗式表格界面配置关键行为。
    """
    
    # 最小和最大行为数量
    MIN_BEHAVIORS = 4
    MAX_BEHAVIORS = 7

    # 预置模板 - 常用场景
    BUILTIN_TEMPLATES = [
        {
            "name": "会议行为分析",
            "description": "识别会议讨论中的各类行为和决策",
            "config": {
                "behaviors": [
                    {"name": "提出需求", "description": "提出新的功能需求或需求变更", "examples": ["我们需要增加一个功能", "这个需求要改一下"]},
                    {"name": "反馈问题", "description": "反馈使用中遇到的问题或Bug", "examples": ["这里有个问题", "运行报错了"]},
                    {"name": "确认事项", "description": "确认需求范围、验收标准或时间节点", "examples": ["就按这个方案来", "这个截止日期没问题"]},
                    {"name": "做出决策", "description": "对讨论事项做出最终决定", "examples": ["我们决定采用这个方案", "就这么定了"]},
                    {"name": "识别风险", "description": "指出潜在的风险和问题", "examples": ["这里有个风险", "可能会出问题"]},
                    {"name": "安排计划", "description": "安排下一步工作和分工", "examples": ["你来负责这部分", "下周一开始做"]},
                ],
                "enable_paragraph_reorganization": True,
                "auto_chunk_long_text": True
            }
        },
        {
            "name": "求职面试分析",
            "description": "识别面试中的自我介绍和项目经验描述",
            "config": {
                "behaviors": [
                    {"name": "项目经验", "description": "描述参与过的项目和职责", "examples": ["我在XX项目负责开发", "这个项目是我主导的"]},
                    {"name": "技能自评", "description": "评价自己的技术能力和掌握程度", "examples": ["我熟练掌握Python", "对云原生比较熟悉"]},
                    {"name": "求职意向", "description": "说明期望的职位和薪资待遇", "examples": ["我期望找Python后端开发", "薪资预期在这个范围"]},
                    {"name": "离职原因", "description": "解释为什么换工作", "examples": ["想寻求更大挑战", "公司业务调整"]},
                    {"name": "提问环节", "description": "面试官或候选人提问", "examples": ["请问这个岗位加班多吗", "你有什么问题要问我"]},
                ],
                "enable_paragraph_reorganization": True,
                "auto_chunk_long_text": True
            }
        },
        {
            "name": "心理咨询记录",
            "description": "识别咨询中的情绪表达和问题描述",
            "config": {
                "behaviors": [
                    {"name": "情绪表达", "description": "表达自己的情绪和感受", "examples": ["我最近感到很焦虑", "压力很大睡不好"]},
                    {"name": "问题描述", "description": "描述遇到的问题和困扰", "examples": ["我和同事关系不好", "这件事一直困扰我"]},
                    {"name": "改变意愿", "description": "表达想要改变的想法", "examples": ["我想调整一下状态", "希望能有所改善"]},
                    {"name": "成长感悟", "description": "分享自己的感悟和收获", "examples": ["通过这段咨询我明白了", "感觉自己成长了很多"]},
                    {"name": "咨询师反馈", "description": "咨询师给出的建议和反馈", "examples": ["你可以试着这样做", "我建议你慢慢来"]},
                ],
                "enable_paragraph_reorganization": True,
                "auto_chunk_long_text": True
            }
        },
        {
            "name": "产品需求沟通",
            "description": "识别需求沟通中的各类行为",
            "config": {
                "behaviors": [
                    {"name": "用户痛点", "description": "描述用户遇到的问题和痛点", "examples": ["用户反馈这个操作太麻烦", "用户经常在这里出错"]},
                    {"name": "功能建议", "description": "提出功能改进建议", "examples": ["我们可以加一个快捷键", "这里应该增加搜索功能"]},
                    {"name": "优先级排序", "description": "对需求进行优先级排序", "examples": ["这个是高优先级", "先做核心功能"]},
                    {"name": "用户故事", "description": "描述用户使用场景", "examples": ["当用户想要搜索的时候", "用户在移动端使用时"]},
                    {"name": "验收标准", "description": "定义需求验收标准", "examples": ["这个需求要满足这些条件", "验收通过的标准是"]},
                ],
                "enable_paragraph_reorganization": True,
                "auto_chunk_long_text": True
            }
        },
        {
            "name": "Leadership Traits (English)",
            "description": "Default 4-key behavior template for leadership assessment (English)",
            "config": {
                "behaviors": [
                    {"name": "Strategic Thinking", "description": "Thinks long-term, sets future goals, takes strategic perspective", "examples": ["I've planned a multi-year roadmap", "This needs to be assessed in advance"]},
                    {"name": "Achievement Orientation", "description": "Strong career ambition, driven to accomplish difficult goals", "examples": ["I am determined to deliver", "Goals must be strictly achieved", "I want to take on challenges"]},
                    {"name": "Critical Analysis", "description": "Critically evaluates information, thinks independently and carefully, identifies potential issues", "examples": ["I think this information may be problematic", "We need more evidence", "Why should we do this"]},
                    {"name": "Leadership Drive", "description": "Willing to take team leadership responsibility, enjoys guiding others, leading and controlling situations", "examples": ["I'll take ownership of the final outcome", "Led the team through the entire process", "I will lead the work planning"]},
                ],
                "enable_paragraph_reorganization": True,
                "auto_chunk_long_text": True
            }
        }
    ]

    def __init__(self, parent: ctk.CTk, on_save: Optional[Callable[[BehaviorConfig], None]] = None,
                 initial_config: Optional[BehaviorConfig] = None):
        """
        初始化对话框

        Args:
            parent: 父窗口
            on_save: 保存时的回调函数
            initial_config: 初始配置（用于编辑已有配置）
        """
        self.parent = parent
        self.on_save = on_save
        self.behaviors: List[BehaviorDefinition] = []
        self.row_widgets: List[dict] = []  # 保存每行输入控件的引用: [{'name': entry, 'desc': entry, 'examples': entry}, ...]

        # 选项设置
        self.enable_paragraph_reorganization = ctk.BooleanVar(value=True)
        self.auto_chunk_long_text = ctk.BooleanVar(value=True)

        # 创建对话框窗口
        self.window = ctk.CTkToplevel(parent)
        self.window.title("⚙ 配置关键行为")
        self.window.geometry("980x680")
        self.window.minsize(880, 600)

        # 模态对话框
        self.window.transient(parent)
        self.window.grab_set()

        # 初始化默认行为
        if initial_config and initial_config.behaviors:
            self.behaviors = list(initial_config.behaviors)
            self.enable_paragraph_reorganization.set(
                getattr(initial_config, 'enable_paragraph_reorganization', True)
            )
            self.auto_chunk_long_text.set(
                getattr(initial_config, 'auto_chunk_long_text', True)
            )
        else:
            self._init_default_behaviors()

        # 创建界面
        self._create_ui()
        
    def _init_default_behaviors(self):
        """初始化默认行为列表（4个）"""
        self.behaviors = [
            BehaviorDefinition(
                name="前瞻思考",
                description="以长远的看法，设定未来的目标，采取战略性的观点",
                examples=["我规划了几年的实现路径", "这事要提前判断"]
            ),
            BehaviorDefinition(
                name="追求成就",
                description="事业心重，具有野心，乐于达成艰巨的目标",
                examples=["我一定要达成", "目标需要严格达成", "我想要挑战"]
            ),
            BehaviorDefinition(
                name="批判分析",
                description="批判性地评估资料，能够进行独立审慎、有根据的思考，寻找潜在问题",
                examples=["我判断这个信息可能有问题", "还需要更多依据", "为什么要这么做"]
            ),
            BehaviorDefinition(
                name="领导意愿",
                description="愿意承担团队领导责任，乐于指导他人、主导及控制局面",
                examples=["我来承担团队的最后结果", "带着团队完成了整个过程", "我来主导工作安排"]
            ),
        ]
        
    def _create_ui(self):
        """创建用户界面"""
        # 主框架
        self.main_frame = ctk.CTkFrame(self.window)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # 标题
        self.title_label = ctk.CTkLabel(
            self.main_frame,
            text="关键行为配置",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=18, weight="bold")
        )
        self.title_label.pack(anchor="w", pady=(0, 5))

        # 说明文本
        self.desc_label = ctk.CTkLabel(
            self.main_frame,
            text=f"配置 {self.MIN_BEHAVIORS}-{self.MAX_BEHAVIORS} 个关键行为，用于识别转录文本中的特定行为模式。",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=11),
            text_color="gray"
        )
        self.desc_label.pack(anchor="w", pady=(0, 10))

        # 高级选项框架
        self.options_frame = ctk.CTkFrame(self.main_frame)
        self.options_frame.pack(fill="x", pady=(0, 10))

        # 选项标题
        self.options_label = ctk.CTkLabel(
            self.options_frame,
            text="高级选项",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=12, weight="bold")
        )
        self.options_label.pack(anchor="w", padx=10, pady=(5, 5))

        # 段落整理复选框
        self.para_reorg_check = ctk.CTkCheckBox(
            self.options_frame,
            text="启用 LLM 段落整理（先清洗再分段，提升匹配质量，消耗额外 Token）",
            variable=self.enable_paragraph_reorganization
        )
        self.para_reorg_check.pack(anchor="w", padx=10, pady=(2, 2))

        # 自动分块复选框
        self.auto_chunk_check = ctk.CTkCheckBox(
            self.options_frame,
            text="自动分块处理超长文本（超过 3万字 自动分割，避免上下文溢出）",
            variable=self.auto_chunk_long_text
        )
        self.auto_chunk_check.pack(anchor="w", padx=10, pady=(2, 5))

        # 行为列表框架
        self.list_frame = ctk.CTkFrame(self.main_frame)
        self.list_frame.pack(fill="both", expand=True, pady=5)

        # 表头
        self._create_table_header()

        # 行为行容器
        self.rows_frame = ctk.CTkScrollableFrame(self.list_frame)
        self.rows_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # 创建行为行
        self._refresh_behavior_rows()

        # 底部按钮栏
        self._create_button_bar()
        
    def _create_table_header(self):
        """创建表格表头"""
        header_frame = ctk.CTkFrame(self.list_frame, fg_color="gray25", height=32)
        header_frame.pack(fill="x", padx=8, pady=(8, 2))
        header_frame.pack_propagate(False)

        # 序号列
        num_label = ctk.CTkLabel(header_frame, text="#", width=30, font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=12, weight="bold"))
        num_label.pack(side="left", padx=6)

        # 名称列
        name_label = ctk.CTkLabel(header_frame, text="行为名称", width=100, font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=12, weight="bold"))
        name_label.pack(side="left", padx=6)

        # 描述列
        desc_label = ctk.CTkLabel(header_frame, text="行为描述", width=240, font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=12, weight="bold"))
        desc_label.pack(side="left", padx=6, fill="x", expand=True)

        # 示例列
        examples_label = ctk.CTkLabel(header_frame, text="示例", width=200, font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=12, weight="bold"))
        examples_label.pack(side="left", padx=6)

        # 操作列
        action_label = ctk.CTkLabel(header_frame, text="操作", width=60, font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=12, weight="bold"))
        action_label.pack(side="left", padx=6)
        
    def _refresh_behavior_rows(self):
        """刷新行为行列表"""
        # 清除现有行
        for widget in self.rows_frame.winfo_children():
            widget.destroy()

        # 清空控件引用列表
        self.row_widgets.clear()

        # 创建新行
        for i, behavior in enumerate(self.behaviors, 1):
            row_widgets = self._create_behavior_row(i, behavior)
            self.row_widgets.append(row_widgets)
            
    def _create_behavior_row(self, index: int, behavior: BehaviorDefinition) -> dict:
        """
        创建单个行为行

        Args:
            index: 行号（从1开始）
            behavior: 行为定义

        Returns:
            包含输入控件引用的字典
        """
        row_frame = ctk.CTkFrame(self.rows_frame, height=62)
        row_frame.pack(fill="x", pady=4)
        row_frame.pack_propagate(False)

        # 序号
        num_label = ctk.CTkLabel(row_frame, text=str(index), width=30)
        num_label.pack(side="left", padx=5)

        # 名称输入
        name_entry = ctk.CTkEntry(row_frame, width=100)
        name_entry.insert(0, behavior.name)
        name_entry.pack(side="left", padx=5)

        # 描述输入
        desc_entry = ctk.CTkEntry(row_frame, width=240)
        desc_entry.insert(0, behavior.description)
        desc_entry.pack(side="left", padx=5, fill="x", expand=True)

        # 示例输入 - 使用多行 Textbox 支持自动换行
        examples_text = "\n".join(behavior.examples) if behavior.examples else ""
        examples_textbox = ctk.CTkTextbox(row_frame, width=200, height=52)
        examples_textbox.insert("1.0", examples_text)
        examples_textbox.pack(side="left", padx=5)

        # 操作按钮框架
        btn_frame = ctk.CTkFrame(row_frame, fg_color="transparent", width=60)
        btn_frame.pack(side="left", padx=5)

        # 删除按钮
        if len(self.behaviors) > self.MIN_BEHAVIORS:
            delete_btn = ctk.CTkButton(
                btn_frame,
                text="×",
                width=25,
                height=25,
                fg_color="red",
                hover_color="darkred",
                command=lambda idx=index-1: self._delete_behavior(idx)
            )
            delete_btn.pack(side="left", padx=2)

        # 返回控件引用
        return {
            'name': name_entry,
            'desc': desc_entry,
            'examples': examples_textbox
        }
        
    def _create_button_bar(self):
        """创建底部按钮栏"""
        btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(10, 5))

        # 最左侧：模板、导入、导出按钮（降低饱和度）
        self.template_btn = ctk.CTkButton(
            btn_frame,
            text="📋 模板",
            command=self._open_template_dialog,
            width=75,
            height=34,
            fg_color="#116666",
            hover_color="#004444"
        )
        self.template_btn.pack(side="left", padx=2)

        self.import_btn = ctk.CTkButton(
            btn_frame,
            text="📥 导入",
            command=self._on_import,
            width=75,
            height=34,
            fg_color="#333366",
            hover_color="#222255"
        )
        self.import_btn.pack(side="left", padx=2)

        self.export_btn = ctk.CTkButton(
            btn_frame,
            text="📤 导出",
            command=self._on_export,
            width=75,
            height=34,
            fg_color="#333366",
            hover_color="#222255"
        )
        self.export_btn.pack(side="left", padx=(2, 15))

        # 左中：添加按钮
        self.add_btn = ctk.CTkButton(
            btn_frame,
            text="+ 添加行为",
            command=self._add_behavior,
            width=100,
            height=34
        )
        self.add_btn.pack(side="left", padx=2)

        # 中间：数量提示
        self.count_label = ctk.CTkLabel(
            btn_frame,
            text=f"当前: {len(self.behaviors)} 个 (最少 {self.MIN_BEHAVIORS}, 最多 {self.MAX_BEHAVIORS})",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=11)
        )
        self.count_label.pack(side="left", padx=15)

        # 右侧：取消和保存按钮（降低饱和度）
        self.cancel_btn = ctk.CTkButton(
            btn_frame,
            text="✖ 取消",
            command=self._on_cancel,
            width=80,
            height=34,
            fg_color="#666666",
            hover_color="#444444"
        )
        self.cancel_btn.pack(side="right", padx=2)

        self.save_btn = ctk.CTkButton(
            btn_frame,
            text="💾 保存配置",
            command=self._on_save,
            width=100,
            height=34,
            fg_color="#224488",
            hover_color="#113366"
        )
        self.save_btn.pack(side="right", padx=2)
        
    # ===== 事件处理方法 =====
    
    def _add_behavior(self):
        """添加新行为"""
        if len(self.behaviors) >= self.MAX_BEHAVIORS:
            messagebox.showwarning(
                "添加失败",
                f"最多只能配置 {self.MAX_BEHAVIORS} 个行为"
            )
            return
            
        # 添加默认行为
        new_behavior = BehaviorDefinition(
            name=f"新行为{len(self.behaviors) + 1}",
            description="请输入行为描述",
            examples=["示例1", "示例2"]
        )
        self.behaviors.append(new_behavior)
        
        # 刷新显示
        self._refresh_behavior_rows()
        self._update_count_label()
        
    def _delete_behavior(self, index: int):
        """
        删除指定索引的行为
        
        Args:
            index: 行为索引
        """
        if len(self.behaviors) <= self.MIN_BEHAVIORS:
            messagebox.showwarning(
                "删除失败",
                f"至少需要保留 {self.MIN_BEHAVIORS} 个行为"
            )
            return
            
        # 确认删除
        if messagebox.askyesno(
            "确认删除",
            f"确定要删除行为 \"{self.behaviors[index].name}\" 吗？"
        ):
            del self.behaviors[index]
            self._refresh_behavior_rows()
            self._update_count_label()
            
    def _update_count_label(self):
        """更新数量标签"""
        self.count_label.configure(
            text=f"当前: {len(self.behaviors)} 个 (最少 {self.MIN_BEHAVIORS}, 最多 {self.MAX_BEHAVIORS})"
        )
        
    def _on_cancel(self):
        """取消按钮点击"""
        self.window.destroy()
        
    def _on_save(self):
        """保存按钮点击"""
        # 从界面收集数据
        updated_behaviors = []
        has_empty = False
        has_unmodified_default = False
        has_special_chars = False
        bad_items = []

        for i, widgets in enumerate(self.row_widgets):
            # 从输入框读取最新值
            name = widgets['name'].get().strip()
            description = widgets['desc'].get().strip()
            # 从 Textbox 读取示例，支持换行分隔
            examples_text = widgets['examples'].get("1.0", "end-1c").strip()

            # 检查是否有空内容
            if not name or not description:
                has_empty = True

            # 检查是否是未修改的默认值（新增行为）
            if (name.startswith('新行为') and name != '说服影响' and name != '质疑追问'
                    and name != '情绪表达' and name != '信息分享'):
                has_unmodified_default = True
            if description == '请输入行为描述':
                has_unmodified_default = True

            # 检查可能导致提示词问题的特殊字符
            # 反引号会破坏prompt格式，多个连续分隔符也可能造成干扰
            if '`' in name or '`' in description or '`' in examples_text or \
               '---' in name or '---' in description or '---' in examples_text or \
               '***' in name or '***' in description or '***' in examples_text:
                has_special_chars = True
                bad_items.append(f"第{i+1}项: {name}")

            # 分割示例 - 支持多种分隔方式：换行、英文分号、中文分号
            # 先按换行分割，如果只有一行再尝试按分号分割
            lines = [ex.strip() for ex in examples_text.splitlines() if ex.strip()]
            if len(lines) == 1 and lines[0]:
                # 如果只有一行，尝试按分号分割
                examples = [ex.strip() for ex in re.split(r'[;；]', lines[0]) if ex.strip()]
            else:
                examples = lines

            # 创建行为定义
            behavior = BehaviorDefinition(
                name=name,
                description=description,
                examples=examples
            )
            updated_behaviors.append(behavior)

        # 创建配置
        config = BehaviorConfig(
            behaviors=updated_behaviors,
            min_confidence=0.6,
            include_context=True,
            context_chars=30,
            enable_paragraph_reorganization=self.enable_paragraph_reorganization.get(),
            auto_chunk_long_text=self.auto_chunk_long_text.get()
        )

        # 验证
        is_valid, msg = config.validate()
        if not is_valid:
            messagebox.showerror("配置无效", msg)
            return

        # 检查空条目提醒
        if has_empty:
            if not messagebox.askyesno(
                "存在空条目",
                "检测到行为名称或描述为空，是否继续保存？"
            ):
                return

        # 检查未修改的默认值提醒
        if has_unmodified_default:
            if not messagebox.askyesno(
                "存在未修改默认值",
                "检测到新增行为仍使用默认名称/描述，是否继续保存？"
            ):
                return

        # 检查特殊字符提醒
        if has_special_chars:
            items_str = "\n".join(bad_items[:5])
            if len(bad_items) > 5:
                items_str += f"\n... 等 {len(bad_items)} 项"
            if not messagebox.askyesno(
                "检测到特殊字符",
                f"以下条目包含可能导致问题的特殊字符（反引号、markdown标记等）:\n{items_str}\n\n这些字符可能干扰LLM解析，建议移除后再保存。是否继续保存？"
            ):
                return

        # 调用保存回调
        if self.on_save:
            self.on_save(config)

        # 关闭对话框
        self.window.destroy()

    # ===== 模板、导入、导出功能 =====

    def _open_template_dialog(self):
        """打开模板选择对话框"""
        dialog = ctk.CTkToplevel(self.window)
        dialog.title("选择预置模板")
        dialog.geometry("400x350")
        dialog.minsize(350, 300)
        dialog.transient(self.window)
        dialog.grab_set()

        # 标题
        title_label = ctk.CTkLabel(
            dialog,
            text="选择预置模板",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=16, weight="bold")
        )
        title_label.pack(padx=20, pady=(15, 5))

        desc_label = ctk.CTkLabel(
            dialog,
            text="选择一个预置模板快速开始，可编辑修改后保存",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=11),
            text_color="gray"
        )
        desc_label.pack(padx=20, pady=(0, 10))

        # 模板列表框架
        list_frame = ctk.CTkScrollableFrame(dialog)
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        def load_template(template_data):
            """加载选中的模板"""
            # 确认会覆盖当前配置
            if self.behaviors and any(b.name != "前瞻思考" for b in self.behaviors):
                if not messagebox.askyesno(
                    "确认加载模板",
                    "加载模板会覆盖当前所有配置。是否继续？"
                ):
                    return

            # 从模板数据创建配置
            template_config = template_data["config"]
            behaviors = []
            for b in template_config.get("behaviors", []):
                behaviors.append(BehaviorDefinition(
                    name=b["name"],
                    description=b["description"],
                    examples=b.get("examples", [])
                ))

            self.behaviors = behaviors
            # 更新高级选项
            self.enable_paragraph_reorganization.set(
                template_config.get("enable_paragraph_reorganization", True)
            )
            self.auto_chunk_long_text.set(
                template_config.get("auto_chunk_long_text", True)
            )

            # 刷新界面
            self._refresh_behavior_rows()
            self._update_count_label()

            # 关闭模板对话框
            dialog.destroy()

            logger.info(f"已加载预置模板: {template_data['name']}")

        # 创建模板按钮列表
        for template in self.BUILTIN_TEMPLATES:
            btn_frame = ctk.CTkFrame(list_frame)
            btn_frame.pack(fill="x", pady=5)

            btn = ctk.CTkButton(
                btn_frame,
                text=f"{template['name']}\n{template['description']}",
                command=lambda t=template: load_template(t),
                height=50
            )
            btn.pack(fill="x", padx=5, pady=5)

    def _on_import(self):
        """导入配置从 JSON 文件"""
        file_path = filedialog.askopenfilename(
            title="导入行为配置",
            filetypes=[("JSON配置文件", "*.json"), ("所有文件", "*.*")],
            initialdir="."
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 验证并创建配置
            config = BehaviorConfig.from_dict(data)
            is_valid, msg = config.validate()
            if not is_valid:
                messagebox.showerror("导入失败", f"配置无效: {msg}")
                return

            # 确认覆盖
            if self.behaviors and any(b.name != "前瞻思考" for b in self.behaviors):
                if not messagebox.askyesno(
                    "确认导入",
                    f"导入会覆盖当前所有配置，共 {len(config.behaviors)} 个行为。是否继续？"
                ):
                    return

            # 加载导入的配置
            self.behaviors = list(config.behaviors)
            self.enable_paragraph_reorganization.set(config.enable_paragraph_reorganization)
            self.auto_chunk_long_text.set(config.auto_chunk_long_text)

            # 刷新界面
            self._refresh_behavior_rows()
            self._update_count_label()

            messagebox.showinfo(
                "导入成功",
                f"成功导入 {len(self.behaviors)} 个行为配置。\n文件: {file_path}"
            )
            logger.info(f"行为配置导入成功: {file_path}, {len(self.behaviors)} 个行为")

        except json.JSONDecodeError as e:
            messagebox.showerror("导入失败", f"JSON 格式错误: {e}")
            logger.error(f"导入配置失败 - JSON格式错误: {e}")
        except Exception as e:
            messagebox.showerror("导入失败", f"发生错误: {e}")
            logger.error(f"导入配置失败: {e}")

    def _on_export(self):
        """导出当前配置到 JSON 文件"""
        # 收集当前配置
        current_behaviors = []
        has_empty = False
        for widgets in self.row_widgets:
            name = widgets['name'].get().strip()
            description = widgets['desc'].get().strip()
            # 从 Textbox 读取示例，支持换行分隔
            examples_text = widgets['examples'].get("1.0", "end-1c").strip()
            # 分割示例 - 支持多种分隔方式：换行、英文分号、中文分号
            lines = [ex.strip() for ex in examples_text.splitlines() if ex.strip()]
            if len(lines) == 1 and lines[0]:
                # 如果只有一行，尝试按分号分割
                examples = [ex.strip() for ex in re.split(r'[;；]', lines[0]) if ex.strip()]
            else:
                examples = lines
            current_behaviors.append({
                "name": name,
                "description": description,
                "examples": examples
            })
            if not name or not description:
                has_empty = True

        # 检查空内容提醒
        if has_empty:
            if not messagebox.askyesno(
                "存在空条目",
                "检测到行为名称或描述为空，是否仍然导出？"
            ):
                return

        # 弹出保存文件对话框
        file_path = filedialog.asksaveasfilename(
            title="导出行为配置",
            defaultextension=".json",
            filetypes=[("JSON配置文件", "*.json"), ("所有文件", "*.*")],
            initialfile="behavior_config.json",
            initialdir="."
        )
        if not file_path:
            return

        try:
            # 创建配置数据
            export_data = {
                "behaviors": current_behaviors,
                "enable_paragraph_reorganization": self.enable_paragraph_reorganization.get(),
                "auto_chunk_long_text": self.auto_chunk_long_text.get(),
                "min_confidence": 0.6,
                "include_context": True,
                "context_chars": 30
            }

            # 写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

            messagebox.showinfo(
                "导出成功",
                f"成功导出 {len(current_behaviors)} 个行为配置。\n文件: {file_path}"
            )
            logger.info(f"行为配置导出成功: {file_path}, {len(current_behaviors)} 个行为")

        except Exception as e:
            messagebox.showerror("导出失败", f"发生错误: {e}")
            logger.error(f"导出配置失败: {e}")


# 测试代码
if __name__ == "__main__":
    import customtkinter as ctk
    
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    
    root = ctk.CTk()
    root.title("主窗口")
    root.geometry("400x300")
    
    def open_dialog():
        dialog = BehaviorConfigDialog(root)
        root.wait_window(dialog.window)
        
    btn = ctk.CTkButton(root, text="打开行为配置", command=open_dialog)
    btn.pack(pady=50)
    
    root.mainloop()
