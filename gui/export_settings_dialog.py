"""
导出设置对话框

提供默认导出选项配置界面，包括：
- 默认导出格式
- 默认输出目录
"""

import sys
import customtkinter as ctk
from tkinter import filedialog
from pathlib import Path
from typing import Optional

from config.settings import settings
from utils.logger import logger

# 默认字体：Windows 使用微软雅黑，其他平台使用系统默认
if sys.platform.startswith('win'):
    DEFAULT_FONT_FAMILY = "Microsoft YaHei"
else:
    # macOS/Linux 使用系统默认字体
    DEFAULT_FONT_FAMILY = None


class ExportSettingsDialog:
    """
    导出设置对话框

    允许用户配置默认导出选项：
    - 默认导出格式
    - 默认输出目录
    """

    def __init__(
        self,
        parent: ctk.CTk,
    ):
        """
        初始化导出设置对话框

        Args:
            parent: 父窗口
        """
        self.parent = parent

        # 创建对话框
        self.window = ctk.CTkToplevel(parent)
        self.window.title("导出设置")
        self.window.geometry("500x350")
        self.window.minsize(450, 300)

        # 模态对话框
        self.window.transient(parent)
        self.window.grab_set()

        # 当前配置
        self.current_output_dir = settings.document.output_dir

        # 创建界面
        self._create_ui()

    def _create_ui(self):
        """创建用户界面"""
        # 使用可滚动框架
        self.main_scroll = ctk.CTkScrollableFrame(self.window)
        self.main_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        self.main_frame = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        self.main_frame.pack(fill="x", expand=True)

        # 标题
        self.title_label = ctk.CTkLabel(
            self.main_frame,
            text="导出设置",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=18, weight="bold")
        )
        self.title_label.pack(anchor="w", pady=(0, 15))

        # 默认输出目录设置
        self._create_output_dir_section()

        # 说明信息
        self._create_info_section()

        # 底部按钮
        self._create_button_bar()

    def _create_output_dir_section(self):
        """创建输出目录设置区域"""
        output_dir_frame = ctk.CTkFrame(self.main_frame)
        output_dir_frame.pack(fill="x", pady=5)

        label = ctk.CTkLabel(
            output_dir_frame,
            text="默认输出目录",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=12, weight="bold")
        )
        label.pack(anchor="w", padx=10, pady=(5, 5))

        # 目录选择框架
        dir_frame = ctk.CTkFrame(output_dir_frame, fg_color="transparent")
        dir_frame.pack(fill="x", padx=10, pady=5)

        self.dir_entry = ctk.CTkEntry(
            dir_frame,
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=11)
        )
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.dir_entry.insert(0, self.current_output_dir)

        self.browse_btn = ctk.CTkButton(
            dir_frame,
            text="浏览...",
            command=self._on_browse,
            width=80
        )
        self.browse_btn.pack(side="right")

    def _create_info_section(self):
        """创建信息说明区域"""
        info_frame = ctk.CTkFrame(self.main_frame)
        info_frame.pack(fill="x", pady=(15, 5))

        info_text = (
            "说明:\n"
            "• 默认输出目录保存在 .env 文件中\n"
            "• 修改后需要重启应用生效\n"
            "• 每次导出时仍可在导出对话框中修改目录"
        )

        info_label = ctk.CTkLabel(
            info_frame,
            text=info_text,
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=10),
            text_color="gray",
            justify="left"
        )
        info_label.pack(anchor="w", padx=10, pady=10)

    def _create_button_bar(self):
        """创建底部按钮栏"""
        button_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(15, 0))

        # 取消按钮
        self.cancel_btn = ctk.CTkButton(
            button_frame,
            text="取消",
            command=self._on_cancel,
            width=100,
            fg_color="gray",
            hover_color="darkgray"
        )
        self.cancel_btn.pack(side="right", padx=5)

        # 保存按钮
        self.save_btn = ctk.CTkButton(
            button_frame,
            text="保存设置",
            command=self._on_save,
            width=120
        )
        self.save_btn.pack(side="right", padx=5)

    def _on_browse(self):
        """浏览按钮点击"""
        directory = filedialog.askdirectory(
            title="选择默认输出目录",
            initialdir=self.dir_entry.get() or "./output"
        )
        if directory:
            self.dir_entry.delete(0, ctk.END)
            self.dir_entry.insert(0, directory)

    def _on_cancel(self):
        """取消按钮点击"""
        self.window.destroy()

    def _on_save(self):
        """保存设置按钮点击"""
        output_dir = self.dir_entry.get().strip()

        if not output_dir:
            from tkinter import messagebox
            messagebox.showwarning("输入错误", "输出目录不能为空")
            return

        # 保存到 .env 文件
        self._save_to_env(output_dir)

        logger.info(f"导出设置已保存: 默认输出目录 = {output_dir}")

        from tkinter import messagebox
        messagebox.showinfo(
            "保存成功",
            f"导出设置已保存:\n默认输出目录: {output_dir}\n\n重启应用后生效。"
        )

        self.window.destroy()

    def _save_to_env(self, output_dir: str):
        """保存设置到 .env 文件

        Args:
            output_dir: 输出目录
        """
        env_path = Path(__file__).parent.parent / ".env"

        if env_path.exists():
            # 读取现有文件
            lines = env_path.read_text(encoding="utf-8").splitlines()
            found = False
            new_lines = []

            for line in lines:
                if line.strip().startswith("OUTPUT_DIR="):
                    new_lines.append(f"OUTPUT_DIR={output_dir}")
                    found = True
                else:
                    new_lines.append(line)

            if not found:
                new_lines.append(f"OUTPUT_DIR={output_dir}")

            env_path.write_text("\n".join(new_lines), encoding="utf-8")
        else:
            # 创建新文件
            env_path.write_text(f"OUTPUT_DIR={output_dir}\n", encoding="utf-8")


# 测试代码
if __name__ == "__main__":
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("测试")
    root.geometry("300x200")

    def open_dialog():
        dialog = ExportSettingsDialog(root)
        root.wait_window(dialog.window)

    btn = ctk.CTkButton(root, text="打开导出设置", command=open_dialog)
    btn.pack(pady=50)

    root.mainloop()
