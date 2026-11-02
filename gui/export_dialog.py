"""
文档导出对话框

提供导出文档的配置界面，包括选择格式、文件名、保存路径等。
记住用户上次选择的输出目录，下次导出默认使用。
"""

import json
import sys
import threading
from queue import Empty, Queue
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

from loguru import logger
from core.formatter.base import FormattedDocument, FormattingStyle
from core.formatter.naming import NamingStrategy
from gui.theme import AppColors, AppFonts

# 获取正确的项目根目录（支持PyInstaller打包）
from config.settings import project_root, settings


class ExportDialog:
    """
    文档导出对话框

    配置导出选项并执行导出。
    """

    # 配置文件路径（存储上次导出路径）
    CONFIG_FILE = project_root / ".export_config.json"

    def __init__(
        self,
        parent: ctk.CTk,
        document: FormattedDocument,
        on_export: Optional[Callable[[Path], None]] = None
    ):
        """
        初始化导出对话框

        Args:
            parent: 父窗口
            document: 要导出的文档
            on_export: 导出完成后的回调
        """
        self.parent = parent
        self.document = document
        self.on_export = on_export
        self.is_exporting = False
        self._closed = False
        self._results = Queue(maxsize=1)
        self._filename_time = datetime.now()

        # 创建对话框
        self.window = ctk.CTkToplevel(parent)
        self.window.title("导出文档")
        self.window.geometry("620x620")
        self.window.minsize(580, 550)

        # 模态对话框
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol('WM_DELETE_WINDOW', self._on_cancel)

        # 导出配置
        self.export_format = ctk.StringVar(value="markdown")
        self.filename_template = ctk.StringVar(value="timestamp_title")
        self.custom_filename = ctk.StringVar()
        # 加载上次保存的输出目录
        self.output_dir = ctk.StringVar(value=self._load_last_output_dir())

        # 创建界面
        self._create_ui()
        for variable in (self.export_format, self.filename_template, self.custom_filename, self.output_dir):
            variable.trace_add('write', lambda *args: self._update_preview())
        self._on_template_change(self.template_menu.get())
        self._update_preview()
        
    def _create_ui(self):
        """创建用户界面"""
        # 使用可滚动框架，确保内容超出时可以滚动浏览
        self.main_scroll = ctk.CTkScrollableFrame(self.window)
        self.main_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        self.main_frame = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        self.main_frame.pack(fill="x", expand=True)

        # 标题
        self.title_label = ctk.CTkLabel(
            self.main_frame,
            text="导出文档配置",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.title_label.pack(anchor="w", pady=(0, 15))

        # 文档信息
        self._create_info_section()

        # 导出格式选择
        self._create_format_section()

        # 文件名设置
        self._create_filename_section()

        # 输出目录
        self._create_output_section()

        # 底部按钮
        self._create_button_bar()
        
    def _create_info_section(self):
        """创建文档信息区域"""
        info_frame = ctk.CTkFrame(self.main_frame)
        info_frame.pack(fill="x", pady=(0, 8))

        # 文档标题
        title = self.document.title or "未命名文档"
        title_label = ctk.CTkLabel(
            info_frame,
            text=f"文档: {title}",
            font=ctk.CTkFont(size=13, weight="bold"), wraplength=510, justify='left'
        )
        title_label.pack(anchor="w", padx=12, pady=(8, 2))

        # 统计信息
        styles = {'raw': '原始转录', 'cleaned': '清理口语', 'paragraphs': '段落整理', 'behavior_match': '行为分析'}
        stats_text = f'字数: {self.document.word_count} | 时长: {int(self.document.duration_seconds)}秒 | 风格: {styles[self.document.style.value]}'
        stats_label = ctk.CTkLabel(
            info_frame,
            text=stats_text,
            font=ctk.CTkFont(*AppFonts.BODY_SMALL),
            text_color=AppColors.TEXT_MUTED
        )
        stats_label.pack(anchor="w", padx=12, pady=(2, 8))

    def _create_format_section(self):
        """创建导出格式选择区域（卡片式布局）"""
        format_frame = ctk.CTkFrame(self.main_frame, fg_color='transparent')
        format_frame.pack(fill="x", pady=(0, 8))

        label = ctk.CTkLabel(
            format_frame,
            text="导出格式",
            font=ctk.CTkFont(*AppFonts.SUBTITLE)
        )
        label.pack(anchor="w", padx=2, pady=(0, 6))

        # 格式选项（卡片式布局，带详细说明）
        formats = [
            {
                "value": "markdown",
                "title": "Markdown",
                "extension": ".md",
                "description": "轻量级格式，带完整行为标记，适合 GitHub、文档网站",
                "icon": "📝",
                "recommended": True
            },
            {
                "value": "docx",
                "title": "Word 文档",
                "extension": ".docx",
                "description": "Microsoft Word 格式，适合正式文档和打印",
                "icon": "📄",
                "recommended": False
            },
            {
                "value": "json",
                "title": "JSON 数据",
                "extension": ".json",
                "description": "结构化数据格式，包含所有元数据和片段信息，适合开发",
                "icon": "🔧",
                "recommended": False
            },
        ]

        self.format_cards = {}
        for fmt in formats:
            card = ctk.CTkFrame(format_frame, corner_radius=8)
            card.pack(fill='x', pady=4)
            self.format_cards[fmt['value']] = card
            radio = ctk.CTkRadioButton(card, text=fmt['title'] + ' (' + fmt['extension'] + ')',
                                       variable=self.export_format, value=fmt['value'], font=AppFonts.BODY,
                                       command=lambda v=fmt['value']: self._on_format_selected(v))
            radio.pack(anchor='w', padx=14, pady=(12, 4))
            description = ctk.CTkLabel(card, text=fmt['description'], font=AppFonts.BODY_SMALL,
                                        text_color=AppColors.TEXT_SECONDARY, wraplength=430,
                                        justify='left', anchor='w')
            description.pack(fill='x', padx=44, pady=(0, 12))

        # 初始化选中状态样式
        self._on_format_selected(self.export_format.get())

    def _on_format_selected(self, format_value: str):
        """格式选中时更新卡片视觉样式"""
        for value, card in self.format_cards.items():
            if value == format_value:
                # 选中状态：使用主色调边框
                card.configure(border_width=2, border_color=AppColors.PRIMARY)
            else:
                # 未选中状态：使用默认边框或无边框
                card.configure(border_width=1, border_color=AppColors.BORDER)

    def _create_filename_section(self):
        """创建文件名设置区域"""
        filename_frame = ctk.CTkFrame(self.main_frame)
        filename_frame.pack(fill="x", pady=(0, 8))

        label = ctk.CTkLabel(
            filename_frame,
            text="文件名设置",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        label.pack(anchor="w", padx=12, pady=(8, 5))

        # 模板选择
        template_label = ctk.CTkLabel(
            filename_frame,
            text="命名模板:",
            font=ctk.CTkFont(size=11)
        )
        template_label.pack(anchor="w", padx=12)
        
        # 模板选项列表: (值, 显示文本)
        templates = [
            ("timestamp", "时间戳 (20240115_143022)"),
            ("timestamp_title", "时间戳_标题 (20240115_143022_会议记录)"),
            ("date_title", "日期_标题 (20240115_会议记录)"),
            ("custom", "自定义"),
        ]
        
        # 创建值到显示文本的映射
        self.template_value_map = {value: text for value, text in templates}
        self.template_text_map = {text: value for value, text in templates}
        
        # 使用显示文本作为选项，但存储值为键
        self.template_menu = ctk.CTkOptionMenu(
            filename_frame,
            values=[text for _, text in templates],
            command=self._on_template_change,
            font=ctk.CTkFont(size=11)
        )
        self.template_menu.pack(fill="x", padx=10, pady=5)
        
        # 默认选中第一个选项
        if templates:
            self.filename_template.set(templates[0][0])
            self.template_menu.set(templates[0][1])
        
        # 自定义文件名输入
        self.custom_filename_frame = ctk.CTkFrame(filename_frame, fg_color="transparent")
        self.custom_filename_frame.pack(fill="x", padx=10, pady=5)
        
        custom_label = ctk.CTkLabel(
            self.custom_filename_frame,
            text="自定义文件名:",
            font=ctk.CTkFont(size=11)
        )
        custom_label.pack(anchor="w")
        
        self.custom_entry = ctk.CTkEntry(
            self.custom_filename_frame,
            textvariable=self.custom_filename,
            font=ctk.CTkFont(size=11)
        )
        self.custom_entry.pack(fill="x", pady=5)
        
    def _create_output_section(self):
        """创建输出目录设置区域"""
        output_frame = ctk.CTkFrame(self.main_frame)
        output_frame.pack(fill="x", pady=(0, 8))

        label = ctk.CTkLabel(
            output_frame,
            text="输出目录",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        label.pack(anchor="w", padx=12, pady=(8, 5))

        # 目录选择框架
        dir_frame = ctk.CTkFrame(output_frame, fg_color="transparent")
        dir_frame.pack(fill="x", padx=12, pady=(0, 8))

        self.dir_entry = ctk.CTkEntry(
            dir_frame,
            textvariable=self.output_dir,
            font=ctk.CTkFont(size=11),
            height=32
        )
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.browse_btn = ctk.CTkButton(
            dir_frame,
            text="浏览...",
            command=self._on_browse,
            width=80,
            height=32,
            fg_color=AppColors.PRIMARY,
            hover_color=AppColors.PRIMARY_HOVER
        )
        self.browse_btn.pack(side="right")
        
    def _create_button_bar(self):
        """创建底部按钮栏"""
        button_frame = ctk.CTkFrame(self.window, fg_color='transparent')
        button_frame.pack(side='bottom', fill='x', padx=20, pady=(4, 16))
        self.path_preview = ctk.CTkLabel(button_frame, text='', wraplength=540, anchor='w',
                                         justify='left', font=AppFonts.BODY_SMALL, text_color=AppColors.TEXT_SECONDARY)
        self.path_preview.pack(fill='x', pady=(0, 8))
        self.export_status = ctk.CTkLabel(button_frame, text='导出当前整理稿；原始会话仍保留。',
                                          anchor='w', font=AppFonts.BODY_SMALL)
        self.export_status.pack(fill='x', pady=(0, 8))

        # 取消按钮
        self.cancel_btn = ctk.CTkButton(
            button_frame,
            text="取消",
            command=self._on_cancel,
            width=90,
            height=36,
            fg_color=AppColors.SECONDARY,
            hover_color=AppColors.SECONDARY_HOVER
        )
        self.cancel_btn.pack(side="right", padx=3)

        # 导出按钮
        self.export_btn = ctk.CTkButton(
            button_frame,
            text="导出",
            command=self._on_export,
            width=110,
            height=36,
            fg_color=AppColors.PRIMARY,
            hover_color=AppColors.PRIMARY_HOVER
        )
        self.export_btn.pack(side="right", padx=3)

    def _load_last_output_dir(self) -> str:
        """
        加载上次保存的输出目录

        Returns:
            保存的目录，如果没有则返回默认
        """
        default_dir = str(settings.document.output_dir)

        if not self.CONFIG_FILE.exists():
            return default_dir

        try:
            with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            last_dir = data.get("last_output_dir")
            if last_dir and Path(last_dir).exists():
                logger.debug(f"加载上次输出目录: {last_dir}")
                return last_dir
            else:
                return default_dir
        except Exception as e:
            logger.warning(f"加载上次输出目录失败，使用默认: {e}")
            return default_dir

    def _save_last_output_dir(self, directory: str) -> None:
        """
        保存当前输出目录到配置文件

        Args:
            directory: 要保存的目录路径
        """
        try:
            data = {
                "last_output_dir": directory
            }
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"保存当前输出目录: {directory}")
        except Exception as e:
            logger.warning(f"保存输出目录配置失败: {e}")

    def _on_browse(self):
        """浏览按钮点击"""
        directory = filedialog.askdirectory(
            title="选择输出目录",
            initialdir=self.output_dir.get() or "./output"
        )
        if directory:
            self.output_dir.set(directory)
            
    def _on_cancel(self):
        """取消按钮点击"""
        if self.is_exporting:
            self.export_status.configure(text='正在写入文档，请等待完成后关闭。')
            return
        self._closed = True
        self.window.destroy()
        
    def _on_export(self):
        if self.is_exporting or self._closed:
            return
        try:
            format_type = self.export_format.get()
            file_path = self._export_path()
            if file_path.exists() and not messagebox.askyesno(
                    '文件已存在', f'文件 {file_path.name} 已存在，是否覆盖？', parent=self.window):
                return
        except Exception as error:
            messagebox.showerror('导出配置无效', str(error), parent=self.window)
            return
        self._set_exporting(True)
        self.export_status.configure(text='正在后台导出，请稍候…')
        self.window.after(80, self._poll_export)
        def export():
            try:
                path = self._do_export(file_path, format_type)
                self._results.put((path, None))
            except Exception as error:
                self._results.put((None, str(error)))
        threading.Thread(target=export, name='document-export', daemon=True).start()

    def _export_path(self):
        extensions = {'markdown': '.md', 'md': '.md', 'docx': '.docx', 'json': '.json'}
        extension = extensions.get(self.export_format.get())
        if extension is None:
            raise ValueError('请选择支持的导出格式')
        directory = self.output_dir.get().strip()
        if not directory:
            raise ValueError('请选择输出目录')
        filename = self._generate_filename()
        if filename.lower().endswith(extension):
            filename = filename[:-len(extension)]
        return Path(directory).expanduser() / f'{filename}{extension}'

    def _update_preview(self):
        try:
            text = f'将保存到：{self._export_path()}'
        except ValueError as error:
            text = str(error)
        self.path_preview.configure(text=text)

    def _set_exporting(self, exporting):
        self.is_exporting = exporting
        def update(parent):
            for widget in parent.winfo_children():
                if isinstance(widget, (ctk.CTkButton, ctk.CTkEntry, ctk.CTkOptionMenu, ctk.CTkRadioButton)):
                    widget.configure(state='disabled' if exporting else 'normal')
                else:
                    update(widget)
        update(self.window)
        self.export_btn.configure(text='正在导出…' if exporting else '导出')

    def _poll_export(self):
        if self._closed:
            return
        try:
            path, error = self._results.get_nowait()
        except Empty:
            self.window.after(80, self._poll_export)
            return
        self._set_exporting(False)
        if error:
            self.export_status.configure(text='导出失败，可检查路径或关闭占用文件后重试。')
            messagebox.showerror('导出失败', error, parent=self.window)
            return
        self._save_last_output_dir(str(path.parent))
        if self.on_export:
            try:
                self.on_export(path)
            except Exception:
                logger.exception('文档已导出，但会话记录更新失败')
                messagebox.showwarning('文档已导出', f'文件已保存到 {path}，但会话导出记录更新失败。', parent=self.window)
        messagebox.showinfo('导出成功', f'文档已导出到：\n{path}', parent=self.window)
        self._on_cancel()
            
    def _generate_filename(self) -> str:
        """
        生成文件名
        
        Returns:
            生成的文件名（不含扩展名）
        """
        template = self.filename_template.get()
        
        if template == "custom":
            # 使用自定义文件名
            custom = self.custom_filename.get().strip()
            if custom:
                return NamingStrategy._sanitize_filename(custom)
            raise ValueError('请输入自定义文件名')
            
        # 使用命名策略生成文件名
        strategy = NamingStrategy(template=template)
        return strategy.generate(
            title=self.document.title or "未命名",
            session_id=self.document.session_id,
            timestamp=self._filename_time,
        )
        
    def _do_export(self, file_path: Path, format_type: str) -> Path:
        """
        执行导出操作

        Args:
            file_path: 导出文件路径
            format_type: 导出格式类型

        Returns:
            最终导出的文件路径（exporter 可能调整扩展名）
        """
        from core.formatter.exporters import JSONExporter, MarkdownExporter, WordExporter

        # 根据格式选择导出器
        if format_type == "json":
            exporter = JSONExporter()
        elif format_type == "markdown" or format_type == "md":
            exporter = MarkdownExporter()
        elif format_type == "docx":
            exporter = WordExporter()
        else:
            raise ValueError(f"不支持的导出格式: {format_type}")

        # 执行导出，返回最终路径（可能被 exporter 调整过扩展名）
        return exporter.export(self.document, file_path)
        
    def set_on_export(self, callback: Callable[[Path], None]):
        """
        设置导出回调
        
        Args:
            callback: 导出完成后的回调函数
        """
        self.on_export = callback
        
    def _on_template_change(self, selected_text: str):
        """
        模板选择变更回调
        
        Args:
            selected_text: 选中的显示文本
        """
        # 将显示文本映射回内部值
        value = self.template_text_map.get(selected_text, "timestamp")
        self.filename_template.set(value)
        
        # 根据是否选择"自定义"显示/隐藏自定义文件名输入框
        if value == "custom":
            self.custom_filename_frame.pack(fill="x", padx=10, pady=5)
        else:
            self.custom_filename_frame.pack_forget()


# 测试代码
if __name__ == "__main__":
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    
    root = ctk.CTk()
    root.title("主窗口")
    root.geometry("400x300")
    
    # 创建测试文档
    from core.formatter.base import FormattedDocument, FormattingStyle
    doc = FormattedDocument(
        title="测试文档",
        raw_text="测试内容",
        formatted_text="格式化后的内容",
        style=FormattingStyle.CLEANED,
        session_id="test_123",
        word_count=100,
        duration_seconds=60.0
    )
    
    def open_dialog():
        dialog = ExportDialog(root, doc)
        root.wait_window(dialog.window)
        
    btn = ctk.CTkButton(root, text="打开导出对话框", command=open_dialog)
    btn.pack(pady=50)
    
    root.mainloop()
