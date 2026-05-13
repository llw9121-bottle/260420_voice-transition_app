"""
API Key 设置对话框

提供图形界面让用户输入阿里云 DashScope API Key，
无需手动编辑 .env 文件。
"""

import sys
import customtkinter as ctk
from tkinter import messagebox
from typing import Optional, Callable

from loguru import logger

from config.settings import save_api_configuration
from gui.theme import AppColors, AppFonts


class APISettingsDialog:
    """
    API Key 设置对话框

    让用户在图形界面中输入 DashScope API Key，
    自动保存到 .env 文件。
    """

    def __init__(
        self,
        parent: ctk.CTk,
        on_save: Optional[Callable[[], None]] = None,
        initial_dashscope: str = "",
        initial_bailian: str = "",
        is_first_launch: bool = False
    ):
        """
        初始化对话框

        Args:
            parent: 父窗口
            on_save: 保存后的回调函数
            initial_dashscope: 初始 DashScope Key
            initial_bailian: 初始 Bailian Key
            is_first_launch: 是否是首次启动引导
        """
        self.parent = parent
        self.on_save = on_save
        self.is_first_launch = is_first_launch

        # 创建对话框窗口
        self.window = ctk.CTkToplevel(parent)
        self.window.title("配置 API Key")
        self.window.geometry("680x540")
        self.window.minsize(620, 480)

        # 模态对话框
        self.window.transient(parent)
        self.window.grab_set()

        # 居中显示
        self._center_window()

        # 创建界面
        self._create_ui(initial_dashscope, initial_bailian)

        logger.info("API 设置对话框已打开")

    def _center_window(self):
        """将窗口居中显示"""
        self.window.update_idletasks()
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()

        width = self.window.winfo_width()
        height = self.window.winfo_height()

        x = parent_x + (parent_width - width) // 2
        y = parent_y + (parent_height - height) // 2
        self.window.geometry(f"+{x}+{y}")

    def _create_ui(self, initial_dashscope: str, initial_bailian: str):
        """创建用户界面"""
        # 使用可滚动框架，保证所有内容都能访问
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.window,
            label_text="",
            corner_radius=0
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # 主框架放在可滚动容器内
        self.main_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # 标题
        title_text = "欢迎使用语音实时转录系统" if self.is_first_launch else "配置 API Key"
        self.title_label = ctk.CTkLabel(
            self.main_frame,
            text=title_text,
            font=ctk.CTkFont(family=AppFonts.FAMILY, size=18, weight="bold")
        )
        self.title_label.pack(anchor="w", pady=(0, 10))

        # 说明文本
        intro_text = """本应用需要阿里云 DashScope 服务进行实时语音识别。
请输入你的 API Key。如果你还没有，可以查看步骤获取。"""
        self.desc_label = ctk.CTkLabel(
            self.main_frame,
            text=intro_text,
            font=ctk.CTkFont(family=AppFonts.FAMILY, size=12),
            text_color=AppColors.TEXT_SECONDARY,
            justify="left"
        )
        self.desc_label.pack(anchor="w", pady=(0, 10))

        # 获取帮助链接提示
        help_text = """获取 API Key 步骤:
1. 访问阿里云 DashScope 控制台: https://dashscope.aliyun.com/
2. 登录或注册阿里云账号
3. 开通 DashScope 服务
4. 在"API Keys"页面创建并复制你的 API Key"""
        self.help_label = ctk.CTkLabel(
            self.main_frame,
            text=help_text,
            font=ctk.CTkFont(family=AppFonts.FAMILY, size=11),
            text_color=AppColors.TEXT_SECONDARY,
            justify="left"
        )
        self.help_label.pack(anchor="w", pady=(0, 15))

        # DashScope API Key 输入框
        self._create_dashscope_input(initial_dashscope)

        # 分隔线
        separator = ctk.CTkFrame(self.main_frame, height=2, fg_color=AppColors.DIVIDER)
        separator.pack(fill="x", pady=10)

        # Bailian API Key (可选)
        self._create_bailian_input(initial_bailian)

        # 提示信息
        hint_text = """提示:
• 如果 BAILIAN_API_KEY 留空，默认使用 DASHSCOPE_API_KEY
• API Key 保存在项目根目录的 .env 文件中
• 保存后需要重启应用才能生效"""
        self.hint_label = ctk.CTkLabel(
            self.main_frame,
            text=hint_text,
            font=ctk.CTkFont(family=AppFonts.FAMILY, size=10),
            text_color=AppColors.TEXT_SECONDARY,
            justify="left"
        )
        self.hint_label.pack(anchor="w", pady=(8, 10))

        # 底部按钮
        self._create_button_bar()

    def _create_dashscope_input(self, initial_value: str):
        """创建 DashScope API Key 输入框（带粘贴按钮和实时校验）"""
        # 标签框架
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        frame.pack(fill="x", pady=5)

        # 标题和状态标签在同一行
        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=5, pady=(2, 5))

        label = ctk.CTkLabel(
            header_frame,
            text="DashScope API Key *",
            font=ctk.CTkFont(*AppFonts.SUBTITLE)
        )
        label.pack(side="left")

        # 校验状态标签
        self.dashscope_status_label = ctk.CTkLabel(
            header_frame,
            text="",
            font=ctk.CTkFont(size=16)
        )
        self.dashscope_status_label.pack(side="left", padx=8)

        # 输入框行：输入框 + 按钮
        input_row = ctk.CTkFrame(frame, fg_color="transparent")
        input_row.pack(fill="x", padx=5, pady=(0, 5))

        self.dashscope_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            show="•",
            height=38
        )
        if initial_value:
            self.dashscope_entry.insert(0, initial_value)
        self.dashscope_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        # 粘贴按钮
        paste_btn = ctk.CTkButton(
            input_row,
            text="📋 粘贴",
            command=self._paste_dashscope_key,
            width=70,
            height=38,
            fg_color=AppColors.PRIMARY,
            hover_color=AppColors.PRIMARY_HOVER
        )
        paste_btn.pack(side="left")

        # 显示/隐藏复选框
        self.show_key_var = ctk.BooleanVar(value=False)
        self.show_check = ctk.CTkCheckBox(
            frame,
            text="显示 API Key",
            variable=self.show_key_var,
            command=self._toggle_show_key,
            font=ctk.CTkFont(*AppFonts.CAPTION)
        )
        self.show_check.pack(anchor="w", padx=5)

        # 绑定输入事件用于实时校验
        self.dashscope_entry.bind("<KeyRelease>", self._validate_dashscope_key)
        # 初始化校验
        self._validate_dashscope_key()

    def _create_bailian_input(self, initial_value: str):
        """创建 Bailian API Key 输入框（带粘贴按钮）"""
        # 标签框架
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        frame.pack(fill="x", pady=5)

        label = ctk.CTkLabel(
            frame,
            text="Bailian API Key (可选)",
            font=ctk.CTkFont(*AppFonts.SUBTITLE)
        )
        label.pack(anchor="w", padx=5, pady=(2, 5))

        # 输入框行：输入框 + 按钮
        input_row = ctk.CTkFrame(frame, fg_color="transparent")
        input_row.pack(fill="x", padx=5, pady=(0, 5))

        self.bailian_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="留空则使用 DashScope API Key",
            show="•",
            height=38
        )
        if initial_value:
            self.bailian_entry.insert(0, initial_value)
        self.bailian_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        # 粘贴按钮
        paste_btn = ctk.CTkButton(
            input_row,
            text="📋 粘贴",
            command=self._paste_bailian_key,
            width=70,
            height=38,
            fg_color=AppColors.SECONDARY,
            hover_color=AppColors.SECONDARY_HOVER
        )
        paste_btn.pack(side="left")

    def _paste_dashscope_key(self):
        """从剪贴板粘贴 DashScope API Key"""
        try:
            text = self.window.clipboard_get()
            self.dashscope_entry.delete(0, "end")
            self.dashscope_entry.insert(0, text.strip())
            self._validate_dashscope_key()
        except Exception as e:
            logger.warning(f"剪贴板粘贴失败: {e}")

    def _paste_bailian_key(self):
        """从剪贴板粘贴 Bailian API Key"""
        try:
            text = self.window.clipboard_get()
            self.bailian_entry.delete(0, "end")
            self.bailian_entry.insert(0, text.strip())
        except Exception as e:
            logger.warning(f"剪贴板粘贴失败: {e}")

    def _validate_dashscope_key(self, event=None):
        """实时校验 DashScope API Key 格式"""
        key = self.dashscope_entry.get().strip()

        if not key:
            # 空输入 - 无状态
            self.dashscope_status_label.configure(text="")
            return

        # 校验规则: 以 sk- 开头，长度合理
        is_valid = key.startswith("sk-") and len(key) >= 20

        if is_valid:
            self.dashscope_status_label.configure(text="✅", text_color=AppColors.SUCCESS)
        else:
            self.dashscope_status_label.configure(text="❌", text_color=AppColors.DANGER)


    def _create_button_bar(self):
        """创建底部按钮栏"""
        btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(10, 5))

        # 取消按钮
        self.cancel_btn = ctk.CTkButton(
            btn_frame,
            text="取消",
            command=self._on_cancel,
            width=100,
            height=40,
            fg_color=AppColors.SECONDARY,
            hover_color=AppColors.SECONDARY_HOVER
        )
        self.cancel_btn.pack(side="right", padx=3)

        # 保存按钮
        self.save_btn = ctk.CTkButton(
            btn_frame,
            text="保存配置",
            command=self._on_save,
            width=130,
            height=40,
            fg_color=AppColors.SUCCESS,
            hover_color=AppColors.SUCCESS_HOVER
        )
        self.save_btn.pack(side="right", padx=3)

    def _toggle_show_key(self):
        """切换显示/隐藏 API Key"""
        if self.show_key_var.get():
            self.dashscope_entry.configure(show="")
            # 也显示bailian
            if hasattr(self, 'bailian_entry'):
                self.bailian_entry.configure(show="")
        else:
            self.dashscope_entry.configure(show="•")
            if hasattr(self, 'bailian_entry'):
                self.bailian_entry.configure(show="•")

    def _on_cancel(self):
        """取消按钮点击"""
        if self.is_first_launch:
            # 首次启动，如果用户取消配置，直接退出应用
            result = messagebox.askyesno(
                "确认退出",
                "未配置 API Key 无法使用应用。\n\n确定要退出吗？"
            )
            if result:
                self.window.destroy()
                # 退出整个应用
                self.parent.quit()
        else:
            self.window.destroy()

    def _on_save(self):
        """保存按钮点击"""
        dashscope_key = self.dashscope_entry.get().strip()
        bailian_key = self.bailian_entry.get().strip()

        # 验证
        if not dashscope_key:
            messagebox.showerror(
                "输入无效",
                "DashScope API Key 不能为空，请输入你的 API Key。"
            )
            return

        # DashScope Key 格式检查（通常以 sk- 开头）
        if not dashscope_key.startswith('sk-'):
            result = messagebox.askyesno(
                "格式警告",
                "DashScope API Key 通常以 'sk-' 开头。\n\n你输入的格式看起来不对，是否仍然继续保存？"
            )
            if not result:
                return

        # 保存配置
        success = save_api_configuration(dashscope_key, bailian_key)
        if not success:
            messagebox.showerror(
                "保存失败",
                "保存配置到 .env 文件失败，请检查权限后重试。"
            )
            return

        # 保存成功
        messagebox.showinfo(
            "保存成功",
            "API 配置已保存成功！\n\n需要重启应用才能生效，请重启应用。"
        )

        logger.info("API 配置已保存，需要重启应用")

        # 调用回调
        if self.on_save:
            self.on_save()

        self.window.destroy()

        # 如果是首次启动，保存成功后退出应用让用户重启
        if self.is_first_launch:
            self.parent.quit()


# 测试代码
if __name__ == "__main__":
    import customtkinter as ctk

    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("主窗口")
    root.geometry("600x400")

    def open_dialog():
        dialog = APISettingsDialog(root, is_first_launch=True)
        root.wait_window(dialog.window)

    btn = ctk.CTkButton(root, text="打开 API 配置", command=open_dialog)
    btn.pack(pady=50)

    root.mainloop()
