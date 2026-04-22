"""
关键行为配置对话框

提供弹窗式表格界面，用于配置 4-7 个关键行为条目。
支持添加、删除、编辑行为定义。
"""

import re
import customtkinter as ctk
from tkinter import messagebox
from typing import List, Optional, Callable

from core.formatter.behavior_matcher import BehaviorDefinition, BehaviorConfig


class BehaviorConfigDialog:
    """
    行为配置对话框
    
    使用弹窗式表格界面配置关键行为。
    """
    
    # 最小和最大行为数量
    MIN_BEHAVIORS = 4
    MAX_BEHAVIORS = 7
    
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

        # 创建对话框窗口
        self.window = ctk.CTkToplevel(parent)
        self.window.title("配置关键行为")
        self.window.geometry("800x600")
        self.window.minsize(700, 500)

        # 模态对话框
        self.window.transient(parent)
        self.window.grab_set()

        # 初始化默认行为
        if initial_config and initial_config.behaviors:
            self.behaviors = list(initial_config.behaviors)
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
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.title_label.pack(anchor="w", pady=(0, 5))
        
        # 说明文本
        self.desc_label = ctk.CTkLabel(
            self.main_frame,
            text=f"配置 {self.MIN_BEHAVIORS}-{self.MAX_BEHAVIORS} 个关键行为，用于识别转录文本中的特定行为模式。",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.desc_label.pack(anchor="w", pady=(0, 10))
        
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
        header_frame = ctk.CTkFrame(self.list_frame, fg_color="gray20", height=30)
        header_frame.pack(fill="x", padx=5, pady=(5, 0))
        header_frame.pack_propagate(False)
        
        # 序号列
        num_label = ctk.CTkLabel(header_frame, text="#", width=30)
        num_label.pack(side="left", padx=5)
        
        # 名称列
        name_label = ctk.CTkLabel(header_frame, text="行为名称", width=120)
        name_label.pack(side="left", padx=5)
        
        # 描述列
        desc_label = ctk.CTkLabel(header_frame, text="描述", width=200)
        desc_label.pack(side="left", padx=5, fill="x", expand=True)
        
        # 示例列
        examples_label = ctk.CTkLabel(header_frame, text="示例", width=150)
        examples_label.pack(side="left", padx=5)
        
        # 操作列
        action_label = ctk.CTkLabel(header_frame, text="操作", width=60)
        action_label.pack(side="left", padx=5)
        
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
        row_frame = ctk.CTkFrame(self.rows_frame, height=40)
        row_frame.pack(fill="x", pady=5)
        row_frame.pack_propagate(False)

        # 序号
        num_label = ctk.CTkLabel(row_frame, text=str(index), width=30)
        num_label.pack(side="left", padx=5)

        # 名称输入
        name_entry = ctk.CTkEntry(row_frame, width=120)
        name_entry.insert(0, behavior.name)
        name_entry.pack(side="left", padx=5)

        # 描述输入
        desc_entry = ctk.CTkEntry(row_frame, width=200)
        desc_entry.insert(0, behavior.description)
        desc_entry.pack(side="left", padx=5, fill="x", expand=True)

        # 示例输入
        examples_text = "; ".join(behavior.examples) if behavior.examples else ""
        examples_entry = ctk.CTkEntry(row_frame, width=150)
        examples_entry.insert(0, examples_text)
        examples_entry.pack(side="left", padx=5)

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
            'examples': examples_entry
        }
        
    def _create_button_bar(self):
        """创建底部按钮栏"""
        btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=10)
        
        # 左侧：添加按钮
        self.add_btn = ctk.CTkButton(
            btn_frame,
            text="+ 添加行为",
            command=self._add_behavior,
            width=120
        )
        self.add_btn.pack(side="left", padx=5)
        
        # 中间：数量提示
        self.count_label = ctk.CTkLabel(
            btn_frame,
            text=f"当前: {len(self.behaviors)} 个 (最少 {self.MIN_BEHAVIORS}, 最多 {self.MAX_BEHAVIORS})",
            font=ctk.CTkFont(size=11)
        )
        self.count_label.pack(side="left", padx=20)
        
        # 右侧：取消和保存按钮
        self.cancel_btn = ctk.CTkButton(
            btn_frame,
            text="取消",
            command=self._on_cancel,
            width=100,
            fg_color="gray",
            hover_color="darkgray"
        )
        self.cancel_btn.pack(side="right", padx=5)
        
        self.save_btn = ctk.CTkButton(
            btn_frame,
            text="保存配置",
            command=self._on_save,
            width=120
        )
        self.save_btn.pack(side="right", padx=5)
        
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
            examples_text = widgets['examples'].get().strip()

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

            # 分割示例 - 同时支持英文分号和中文分号
            examples = [ex.strip() for ex in re.split(r'[;；]', examples_text) if ex.strip()]

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
            context_chars=30
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
