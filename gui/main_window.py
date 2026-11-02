"""
主窗口模块

提供基于 CustomTkinter 的主应用程序窗口。
"""

import json
import sys
import tkinter as tk
import customtkinter as ctk
from pathlib import Path
from typing import Optional, Callable

from config.settings import settings, project_root
from core.formatter.base import FormattedDocument, FormattingStyle
from core.formatter.behavior_matcher import BehaviorConfig
from gui.theme import AppColors, AppFonts
from core.recording_state import RecordingState
from gui.review_workspace import ReviewWorkspace
from utils.logger import logger


class MainWindow:
    """
    主窗口类
    
    创建和管理应用程序的主界面。
    """
    
    STYLE_LABELS = {'原始转录': 'raw', '清理口语': 'cleaned', '段落整理': 'paragraphs', '行为分析': 'behavior_match'}
    STYLE_HINTS = {'raw': '保留转录原文，不调用 AI。', 'cleaned': '轻量清理口语，原文始终保留。',
                   'paragraphs': '按停顿分段；可选择 AI 语义分段。', 'behavior_match': '依据行为定义分析引文，会调用 AI。'}

    def __init__(self):
        """初始化主窗口"""
        # 配置文件路径（存储用户偏好）
        self.USER_CONFIG_FILE = project_root / ".user_config.json"

        # 加载保存的用户偏好设置
        saved_config = self._load_user_config()
        saved_theme = saved_config.get("appearance_mode", "System")
        saved_font_size = saved_config.get("font_size", 16)

        # 设置 CustomTkinter 外观
        ctk.set_appearance_mode(saved_theme)
        ctk.set_default_color_theme("blue")  # blue, green, dark-blue
        ctk.ThemeManager.theme['CTkFont']['family'] = AppFonts.FAMILY

        # 创建主窗口（必须先创建 root 才能创建 StringVar）
        self.root = ctk.CTk()
        self.root.configure(fg_color=AppColors.BACKGROUND)
        self.root.title("语音实时转录系统")
        self.root.geometry("1280x840")
        self.root.minsize(840, 640)

        # 创建主题变量（必须在 root 创建之后）
        self.appearance_mode = ctk.StringVar(value=saved_theme)
        # 创建字体大小变量
        self.font_size = ctk.IntVar(value=saved_font_size)

        # 从用户配置加载 ASR 设置，如果没有则使用默认配置
        from config.settings import settings
        self.saved_language = saved_config.get("asr_language", settings.asr.language)
        self.saved_vad_ms = saved_config.get("vad_silence_ms", settings.asr.vad_silence_ms)

        # 存储回调函数
        self.on_start_callback: Optional[Callable] = None
        self.on_stop_callback: Optional[Callable] = None
        self.on_pause_callback: Optional[Callable] = None
        self.on_resume_callback: Optional[Callable] = None
        self.on_export_callback: Optional[Callable] = None
        self.on_behavior_config_callback: Optional[Callable[[Optional[BehaviorConfig]], None]] = None

        # 存储设备列表
        self.available_devices: list[tuple[Optional[int], str]] = []
        self.selected_device_index: Optional[int] = None

        # 创建界面
        self._create_ui()

        # 绑定键盘快捷键
        self._bind_shortcuts()
        self.set_recording_state(RecordingState.READY)

        # 启动后延迟刷新设备列表，避免卡顿
        self.root.after(100, self._refresh_devices)
        
    def _create_ui(self):
        """创建用户界面"""
        # 创建网格布局
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        
        # 主框架
        self.main_frame = ctk.CTkFrame(self.root, fg_color='transparent')
        self.main_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)
        
        # 顶部控制栏
        self._create_control_bar()
        
        # 中间内容区
        self._create_content_area()
        
        # 底部状态栏
        self._create_status_bar()
        
    def _create_control_bar(self):
        self.control_frame = ctk.CTkFrame(self.main_frame, fg_color='transparent')
        self.control_frame.grid(row=0, column=0, padx=16, pady=(16, 12), sticky='ew')
        self.control_frame.grid_columnconfigure(0, weight=1)
        title = ctk.CTkFrame(self.control_frame, fg_color='transparent')
        title.grid(row=0, column=0, sticky='ew', pady=(0, 14))
        self.title_label = ctk.CTkLabel(title, text='语音工作台', font=AppFonts.HEADING)
        self.title_label.pack(side='left')
        self.help_btn = ctk.CTkButton(title, text='帮助', command=self._show_help, width=60, fg_color='transparent', text_color=AppColors.TEXT_PRIMARY, hover_color=AppColors.SURFACE)
        self.help_btn.pack(side='right', padx=(8, 0))
        self.settings_btn = ctk.CTkButton(title, text='设置', command=self._show_settings, width=60, fg_color='transparent', text_color=AppColors.TEXT_PRIMARY, hover_color=AppColors.SURFACE)
        self.settings_btn.pack(side='right', padx=(8, 0))
        self.history_btn = ctk.CTkButton(title, text='会话历史', command=lambda: self.workspace._call('history'), width=88, fg_color='transparent', text_color=AppColors.TEXT_PRIMARY, hover_color=AppColors.SURFACE)
        self.history_btn.pack(side='right')
        self.button_frame = ctk.CTkFrame(self.control_frame, fg_color='transparent')
        self.button_frame.grid(row=1, column=0, sticky='ew')
        self.start_btn = ctk.CTkButton(self.button_frame, text='开始录音', command=self._on_start_click, width=112, height=38, fg_color=AppColors.PRIMARY, hover_color=AppColors.PRIMARY_HOVER)
        self.start_btn.pack(side='left', padx=(0, 8))
        self.pause_btn = ctk.CTkButton(self.button_frame, text='暂停', command=self._on_pause_click, width=80, height=38, fg_color='transparent', border_width=1, border_color=AppColors.BORDER, text_color=AppColors.TEXT_PRIMARY, hover_color=AppColors.SURFACE)
        self.pause_btn.pack(side='left', padx=(0, 8))
        self.stop_btn = ctk.CTkButton(self.button_frame, text='结束录音', command=self._on_stop_click, width=92, height=38, fg_color='transparent', border_width=1, border_color=AppColors.BORDER, text_color=AppColors.DANGER, hover_color=AppColors.SURFACE)
        self.stop_btn.pack(side='left', padx=(0, 8))
        self.export_btn = ctk.CTkButton(self.button_frame, text='导出文稿', command=self._on_export_click, width=92, height=38, fg_color='transparent', border_width=1, border_color=AppColors.BORDER, text_color=AppColors.TEXT_PRIMARY, hover_color=AppColors.SURFACE)
        self.export_btn.pack(side='right')
        self.help_hint_label = ctk.CTkLabel(self.button_frame, text='空格 开始 / 暂停 · Esc 结束', font=AppFonts.BODY_SMALL, text_color=AppColors.TEXT_SECONDARY)
        self.help_hint_label.pack(side='left', padx=12)

    def _create_content_area(self):
        self.content_frame = ctk.CTkFrame(self.main_frame, fg_color='transparent')
        self.content_frame.grid(row=1, column=0, padx=16, pady=0, sticky='nsew')
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)
        self._create_transcription_area()
        self.settings_window = ctk.CTkToplevel(self.root)
        self.settings_window.withdraw()
        self.settings_window.title('录音与整理设置')
        self.settings_window.geometry('460x720')
        self.settings_window.minsize(400, 500)
        self.settings_window.transient(self.root)
        self.settings_window.protocol('WM_DELETE_WINDOW', self.settings_window.withdraw)
        self.settings_scroll_frame = ctk.CTkScrollableFrame(self.settings_window, label_text='录音与整理设置', label_font=AppFonts.TITLE)
        self.settings_scroll_frame.pack(fill='both', expand=True, padx=16, pady=16)
        self._create_settings_panel()
        ctk.CTkLabel(self.settings_frame, text='阅读字号', font=AppFonts.SUBTITLE).pack(anchor='w', padx=18, pady=(16, 6))
        self.font_size_menu = ctk.CTkOptionMenu(self.settings_frame, values=['16', '18', '20', '22', '24'], variable=self.font_size, command=self._on_font_size_change)
        self.font_size_menu.pack(fill='x', padx=18, pady=(0, 16))

    def _create_transcription_area(self):
        self.workspace = ReviewWorkspace(self.content_frame, font_size=self.font_size.get())
        self.workspace.grid(row=0, column=0, sticky='nsew')
        self.transcription_text = self.workspace.raw_text
        self.search_entry = self.workspace.search_entry
        self.scroll_lock_var = self.workspace.scroll_lock_var

    def _show_settings(self):
        self.settings_window.deiconify()
        self.settings_window.lift()
        self.settings_window.focus_force()

    def show_document(self, document, revisions, audio_available=False, audio_hint=None):
        self.workspace.show_document(document, revisions, audio_available, audio_hint)

    def render_live(self, confirmed, partial, segments):
        self.workspace.render_live(confirmed, partial, segments)

    def _create_settings_panel(self):
        """创建设置面板（放在可滚动框架内）"""
        # settings_frame 放在可滚动框架内部
        self.settings_frame = ctk.CTkFrame(self.settings_scroll_frame, fg_color="transparent")
        self.settings_frame.pack(fill="both", expand=True)

        # 卡片 1: 格式化风格（最常用，放上方）
        style_card = ctk.CTkFrame(self.settings_frame)
        style_card.pack(fill="x", padx=8, pady=5)
        style_inner = ctk.CTkFrame(style_card, fg_color="transparent")
        style_inner.pack(fill="x", padx=10, pady=10)

        self.style_label = ctk.CTkLabel(
            style_inner,
            text="格式化风格",
            font=ctk.CTkFont(*AppFonts.SUBTITLE)
        )
        self.style_label.pack(anchor="w", pady=(0, 6))

        self.style_var = ctk.StringVar(value="清理口语")
        self.style_menu = ctk.CTkOptionMenu(
            style_inner,
            values=list(self.STYLE_LABELS),
            variable=self.style_var,
            command=self._on_style_change,
            height=32
        )
        self.style_menu.pack(fill="x", pady=(0, 6))

        # 段落选项：LLM语义分段（仅paragraphs模式可用
        self.llm_para_var = ctk.BooleanVar(value=False)
        self.llm_para_check = ctk.CTkCheckBox(
            style_inner,
            text="使用 AI 语义分段（段落整理模式）",
            variable=self.llm_para_var,
            onvalue=True,
            offvalue=False
        )
        self.llm_para_check.pack(anchor="w")
        self.style_hint = ctk.CTkLabel(style_inner, text="轻量清理口语，原文始终保留。", wraplength=320, justify="left", text_color=AppColors.TEXT_SECONDARY)
        self.style_hint.pack(anchor="w", pady=(8, 0))

        # 卡片 2: 功能按钮区
        buttons_card = ctk.CTkFrame(self.settings_frame)
        buttons_card.pack(fill="x", padx=8, pady=5)
        buttons_inner = ctk.CTkFrame(buttons_card, fg_color="transparent")
        buttons_inner.pack(fill="x", padx=10, pady=10)

        # 行为匹配配置按钮
        self.behavior_btn = ctk.CTkButton(
            buttons_inner,
            text="配置关键行为",
            command=self._on_behavior_config_click,
            height=34
        )
        self.behavior_btn.pack(fill="x", pady=(0, 6))

        # 导出设置按钮
        self.export_settings_btn = ctk.CTkButton(
            buttons_inner,
            text="导出设置",
            command=self._on_export_settings_click,
            height=34
        )
        self.export_settings_btn.pack(fill="x")

        # 卡片 3: 音频选项
        audio_card = ctk.CTkFrame(self.settings_frame)
        audio_card.pack(fill="x", padx=8, pady=5)
        audio_inner = ctk.CTkFrame(audio_card, fg_color="transparent")
        audio_inner.pack(fill="x", padx=10, pady=10)

        self.save_audio_label = ctk.CTkLabel(
            audio_inner,
            text="音频选项",
            font=ctk.CTkFont(*AppFonts.SUBTITLE)
        )
        self.save_audio_label.pack(anchor="w", pady=(0, 8))

        self.save_audio_var = ctk.BooleanVar(value=True)
        self.save_audio_switch = ctk.CTkSwitch(
            audio_inner,
            text="保存原始音频(WAV)",
            variable=self.save_audio_var,
            onvalue=True,
            offvalue=False,
            command=self._on_save_audio_change
        )
        self.save_audio_switch.pack(anchor="w")

        # 卡片 4: ASR 识别设置
        asr_card = ctk.CTkFrame(self.settings_frame)
        asr_card.pack(fill="x", padx=8, pady=5)
        asr_inner = ctk.CTkFrame(asr_card, fg_color="transparent")
        asr_inner.pack(fill="x", padx=10, pady=10)

        self.asr_label = ctk.CTkLabel(
            asr_inner,
            text="识别设置",
            font=ctk.CTkFont(*AppFonts.SUBTITLE)
        )
        self.asr_label.pack(anchor="w", pady=(0, 8))

        # 语言选择
        self.language_label = ctk.CTkLabel(
            asr_inner,
            text="识别语言:",
            font=ctk.CTkFont(*AppFonts.BODY_SMALL)
        )
        self.language_label.pack(anchor="w", padx=5, pady=(0, 4))

        # 常用语言列表，按使用频率排序
        language_options = [
            "zh - 中文",
            "yue - 粤语",
            "en - 英文",
            "ja - 日语",
            "ko - 韩语",
            "de - 德语",
            "fr - 法语",
            "es - 西班牙语",
            "ru - 俄语",
            "other"
        ]
        # 找到匹配用户保存语言的选项
        default_language_display = language_options[0]
        for opt in language_options:
            if opt.startswith(self.saved_language + " "):
                default_language_display = opt
                break
        self.language_var = ctk.StringVar(value=default_language_display)
        self.language_menu = ctk.CTkOptionMenu(
            asr_inner,
            values=language_options,
            variable=self.language_var,
            command=self._on_language_change,
            height=32,
            font=ctk.CTkFont(*AppFonts.BODY_SMALL)
        )
        self.language_menu.pack(fill="x", padx=5, pady=(0, 10))

        # VAD 静音检测时长
        self.vad_label = ctk.CTkLabel(
            asr_inner,
            text=f"断句灵敏度: {self.saved_vad_ms} ms",
            font=ctk.CTkFont(family=AppFonts.FAMILY, size=11)
        )
        self.vad_label.pack(anchor="w", padx=5, pady=(0, 4))

        self.vad_silence_var = ctk.IntVar(value=self.saved_vad_ms)
        self.vad_slider = ctk.CTkSlider(
            asr_inner,
            from_=200,
            to=2000,
            number_of_steps=18,  # 200-2000 每步100
            variable=self.vad_silence_var,
            command=self._on_vad_change
        )
        self.vad_slider.pack(fill="x", padx=5, pady=(0, 4))

        self.vad_hint_label = ctk.CTkLabel(
            asr_inner,
            text="短=灵敏快断  长=稳定少断",
            font=ctk.CTkFont(AppFonts.FAMILY, 9),
            text_color=AppColors.TEXT_MUTED
        )
        self.vad_hint_label.pack(anchor="e", padx=5)

        # 卡片 5: 音频输入设备选择
        device_card = ctk.CTkFrame(self.settings_frame)
        device_card.pack(fill="x", padx=8, pady=5)
        device_inner = ctk.CTkFrame(device_card, fg_color="transparent")
        device_inner.pack(fill="x", padx=10, pady=10)

        self.device_label = ctk.CTkLabel(
            device_inner,
            text="音频输入设备",
            font=ctk.CTkFont(*AppFonts.SUBTITLE)
        )
        self.device_label.pack(anchor="w", pady=(0, 8))

        # 设备选择框架 - 下拉框和刷新按钮并排显示
        self.device_frame = ctk.CTkFrame(device_inner, fg_color="transparent")
        self.device_frame.pack(fill="x")
        self.device_frame.grid_columnconfigure(0, weight=1)
        self.device_frame.grid_columnconfigure(1, weight=0)

        self.device_var = ctk.StringVar(value="默认设备")
        self.device_menu = ctk.CTkOptionMenu(
            self.device_frame,
            values=["加载中..."],
            variable=self.device_var,
            command=self._on_device_change,
            height=32
        )
        self.device_menu.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        # 刷新设备按钮
        self.refresh_device_btn = ctk.CTkButton(
            self.device_frame,
            text="刷新",
            command=self._refresh_devices,
            height=32,
            width=60
        )
        self.refresh_device_btn.grid(row=0, column=1, sticky="e")

        # 存储设备列表
        self.available_devices: list[tuple[int, str]] = []  # (index, name)
        self.selected_device_index: Optional[int] = None

        # 卡片 6: API 设置
        api_card = ctk.CTkFrame(self.settings_frame)
        api_card.pack(fill="x", padx=8, pady=5)
        api_inner = ctk.CTkFrame(api_card, fg_color="transparent")
        api_inner.pack(fill="x", padx=10, pady=10)

        # API 设置按钮
        self.api_settings_btn = ctk.CTkButton(
            api_inner,
            text="设置 API Key",
            command=self._open_api_settings,
            height=34,
            fg_color=AppColors.ACCENT,
            hover_color=AppColors.ACCENT_HOVER
        )
        self.api_settings_btn.pack(fill="x")
        
    def _create_status_bar(self):
        """创建底部状态栏（优化高度和布局）"""
        self.status_frame = ctk.CTkFrame(self.main_frame, height=44, fg_color=AppColors.SURFACE)
        self.status_frame.grid(row=2, column=0, padx=12, pady=(6, 10), sticky="ew")
        self.status_frame.grid_propagate(False)

        # 左侧：状态指示区域
        left_frame = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        left_frame.pack(side="left", fill="y", padx=(12, 0))

        # 录音状态指示灯（脉冲动画效果）
        self.recording_indicator = ctk.CTkLabel(
            left_frame,
            text="●",
            font=ctk.CTkFont(AppFonts.FAMILY, 20),
            text_color=AppColors.RECORDING_INDICATOR_OFF
        )
        self.recording_indicator.pack(side="left", pady=8)

        # 状态标签
        self.status_label = ctk.CTkLabel(
            left_frame,
            text="就绪",
            font=ctk.CTkFont(*AppFonts.BODY)
        )
        self.status_label.pack(side="left", padx=(10, 0), pady=8)

        # 右侧：控制和信息区域
        right_frame = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        right_frame.pack(side="right", fill="y", padx=(0, 12))

        # 音量指示器区域
        volume_container = ctk.CTkFrame(right_frame, fg_color="transparent")
        volume_container.pack(side="right", padx=(8, 0))

        # 音量标签
        self.volume_label = ctk.CTkLabel(
            volume_container,
            text="音量:",
            font=ctk.CTkFont(*AppFonts.BODY_SMALL),
            text_color=AppColors.TEXT_MUTED
        )
        self.volume_label.pack(side="left", pady=8)

        # 音量进度条
        self.volume_bar = ctk.CTkProgressBar(
            volume_container,
            width=80,
            height=14,
            corner_radius=3
        )
        self.volume_bar.set(0)
        self.volume_bar.pack(side="left", padx=(4, 0), pady=8)

        # 主题选择区域
        theme_container = ctk.CTkFrame(right_frame, fg_color="transparent")
        theme_container.pack(side="right", padx=(8, 0))

        self.theme_label = ctk.CTkLabel(
            theme_container,
            text="主题:",
            font=ctk.CTkFont(*AppFonts.BODY_SMALL),
            text_color=AppColors.TEXT_MUTED
        )
        self.theme_label.pack(side="left", pady=8)

        self.theme_menu = ctk.CTkOptionMenu(
            theme_container,
            values=["System", "Light", "Dark"],
            variable=self.appearance_mode,
            command=self._on_theme_change,
            width=82,
            height=26,
            font=ctk.CTkFont(*AppFonts.CAPTION)
        )
        self.theme_menu.pack(side="left", padx=(4, 0), pady=8)

        # 时长标签（等宽字体确保数字对齐不跳动）
        self.duration_label = ctk.CTkLabel(
            right_frame,
            text="00:00",
            font=ctk.CTkFont(AppFonts.MONOSPACE, 14, weight='bold')
        )
        self.duration_label.pack(side="right", padx=(0, 8), pady=8)

        # 闪烁动画控制
        self._is_recording_flashing = False
        self._recording_indicator_timer_id = None

    def _on_start_click(self):
        """开始按钮点击"""
        if not self.recording_state.busy and self.on_start_callback:
            self.on_start_callback()

    def _on_pause_click(self):
        """暂停/继续按钮点击"""
        if self.recording_state == RecordingState.PAUSED:
            if self.on_resume_callback:
                self.on_resume_callback()
        elif self.recording_state.captures_audio and self.on_pause_callback:
            self.on_pause_callback()

    def _on_stop_click(self):
        """停止按钮点击"""
        if self.recording_state.captures_audio and self.on_stop_callback:
            self.on_stop_callback()

    def set_recording_state(self, state: RecordingState) -> None:
        """只由应用确认的生命周期驱动按钮、设置和录音指示灯。"""
        self.recording_state = state
        labels = {
            RecordingState.READY: '就绪', RecordingState.CONNECTING: '正在连接语音服务…',
            RecordingState.RECORDING: '正在录音', RecordingState.PAUSED: '已暂停',
            RecordingState.RECONNECTING: '连接中断，正在尝试恢复',
            RecordingState.STOPPING: '正在结束录音并保存会话…',
            RecordingState.PROCESSING: '正在处理，请稍候…',
            RecordingState.SAVED: '会话已保存', RecordingState.ERROR: '操作失败，可重试',
        }
        self.start_btn.configure(state='disabled' if state.busy else 'normal')
        self.pause_btn.configure(
            state='normal' if state.captures_audio else 'disabled',
            text='继续' if state == RecordingState.PAUSED else '暂停',
        )
        self.stop_btn.configure(state='normal' if state.captures_audio else 'disabled')
        self.export_btn.configure(state='disabled' if state.busy else 'normal')
        for widget in (
            self.device_menu, self.refresh_device_btn, self.language_menu,
            self.vad_slider, self.save_audio_switch, self.style_menu,
            self.llm_para_check, self.behavior_btn, self.api_settings_btn,
        ):
            widget.configure(state='disabled' if state.busy else 'normal')
        self.set_recording_indicator(state in {RecordingState.RECORDING, RecordingState.RECONNECTING})
        self.update_status(labels[state])
        if hasattr(self, 'workspace'):
            self.workspace.set_busy(state.busy)
            self.history_btn.configure(state='disabled' if state.busy else 'normal')
        if hasattr(self, 'style_var') and not state.busy:
            self.llm_para_check.configure(state='normal' if self.get_selected_style() == 'paragraphs' else 'disabled')
            
    def _on_export_click(self):
        """导出按钮点击"""
        if self.on_export_callback:
            self.on_export_callback()
            
    def _on_style_change(self, choice):
        """格式化风格改变"""
        logger.info(f"格式化风格已更改为: {choice}")

        # 如果用户切换到 behavior_match 且尚未配置行为，提示打开配置界面
        self.llm_para_check.configure(state="normal" if self.get_selected_style() == "paragraphs" else "disabled")
        self.style_hint.configure(text=self.STYLE_HINTS[self.get_selected_style()])
        if self.get_selected_style() == "behavior_match" and self.on_behavior_config_callback is not None:
            import tkinter.messagebox as messagebox
            result = messagebox.askyesno(
                "配置关键行为",
                "您选择了「行为匹配」格式化风格。\n\n行为匹配需要您先定义要识别的关键行为。\n\n是否现在打开配置界面？"
            )
            if result:
                self._on_behavior_config_click()
        self.update_status('风格已切换；点击“重新整理”后应用到当前文档')

    def set_review_style(self, style, llm_paragraphs=False):
        label = next((label for label, code in self.STYLE_LABELS.items() if code == style), '原始转录')
        self.style_var.set(label)
        self.llm_para_var.set(bool(llm_paragraphs))
        self.style_hint.configure(text=self.STYLE_HINTS[self.get_selected_style()])
        self.llm_para_check.configure(state='normal' if style == 'paragraphs' else 'disabled')

    def _on_device_change(self, choice):
        """音频设备改变"""
        # 根据选中的名称找到设备索引
        for idx, (device_index, device_name) in enumerate(self.available_devices):
            display_name = f"{device_index}: {device_name}"
            if display_name == choice:
                self.selected_device_index = device_index
                logger.info(f"已选择音频设备: {device_name} (索引: {device_index})")
                break

    def _on_save_audio_change(self):
        """保存音频选项改变"""
        enabled = self.save_audio_var.get()
        if enabled:
            logger.info("保存原始音频已开启")
        else:
            logger.info("保存原始音频已关闭")

    def _on_language_change(self, choice: str):
        """语言选择改变"""
        # 从显示文本中提取语言代码 (例如 "zh - 中文" -> "zh")
        lang_code = choice.split()[0]
        logger.info(f"识别语言已更改为: {choice}")

    def _on_vad_change(self, value: float):
        """VAD 滑块值改变"""
        ms = int(value)
        self.vad_label.configure(text=f"断句灵敏度: {ms} ms")
        logger.debug(f"VAD 静音检测时长已调整: {ms} ms")

    def _bind_shortcuts(self):
        """绑定键盘快捷键"""
        # 空格键: 开始/停止录音
        self.root.bind('<space>', self._on_space_shortcut)
        # Esc: 停止录音
        self.root.bind('<Escape>', self._on_escape_shortcut)
        # Ctrl+S: 导出文档（所有平台）
        self.root.bind('<Control-s>', self._on_ctrl_s_shortcut)
        # Command+S: 导出文档（macOS 习惯）
        self.root.bind('<Command-s>', self._on_ctrl_s_shortcut)
        # Ctrl+B: 打开行为配置（所有平台）
        self.root.bind('<Control-b>', self._on_ctrl_b_shortcut)
        # Command+B: 打开行为配置（macOS 习惯）
        self.root.bind('<Command-b>', self._on_ctrl_b_shortcut)
        # F1: 打开帮助
        self.root.bind('<F1>', self._on_f1_shortcut)
        self.root.bind('<Control-f>', lambda event: self.workspace.search_entry.focus_set())
        self.root.bind('<Command-f>', lambda event: self.workspace.search_entry.focus_set())

    def _on_space_shortcut(self, event):
        """空格键快捷键处理"""
        # 文本输入控件保留空格输入，不触发录音快捷键。
        focused = self.root.focus_get()
        if isinstance(focused, (tk.Entry, tk.Text, tk.Spinbox)):
            return

        if self.start_btn.cget('state') == 'normal':
            self._on_start_click()
        elif self.pause_btn.cget('state') == 'normal':
            self._on_pause_click()
        elif self.stop_btn.cget('state') == 'normal':
            self._on_stop_click()

    def _on_escape_shortcut(self, event):
        """Esc快捷键处理 - 停止录音"""
        if self.stop_btn.cget('state') == 'normal':
            self._on_stop_click()

    def _on_ctrl_s_shortcut(self, event):
        """Ctrl+S快捷键处理 - 导出文档"""
        if self.on_export_callback:
            self.on_export_callback()

    def _on_ctrl_b_shortcut(self, event):
        """Ctrl+B快捷键处理 - 行为配置"""
        if not self.recording_state.busy:
            self._on_behavior_config_click()

    def _on_f1_shortcut(self, event):
        """F1快捷键处理 - 打开帮助"""
        self._show_help()

    def _refresh_devices(self):
        """刷新可用音频设备列表"""
        from core.audio_recorder import AudioRecorder

        try:
            recorder = AudioRecorder()
            devices = recorder.list_devices()
            recorder.audio.terminate()

            self.available_devices = []
            display_names = []

            # 添加默认设备选项（None表示使用系统默认）
            self.available_devices.append((None, "默认设备"))
            display_names.append("默认设备")

            # 添加所有检测到的设备
            for device in devices:
                self.available_devices.append((device.index, device.name))
                # 显示名称包含索引便于识别
                display_name = f"{device.index}: {device.name}"
                display_names.append(display_name)

            # 更新下拉菜单
            self.device_menu.configure(values=display_names)
            self.device_var.set(display_names[0])
            self.selected_device_index = None

            logger.info(f"刷新音频设备列表完成，共 {len(devices) + 1} 个选项")

        except Exception as e:
            logger.error(f"刷新音频设备列表失败: {e}")
            self.update_status(f"刷新设备失败: {e}")
        
    def _on_behavior_config_click(self, initial_config=None):
        """行为配置按钮点击"""
        from gui.behavior_config_dialog import BehaviorConfigDialog

        def on_save(config):
            if self.on_behavior_config_callback:
                self.on_behavior_config_callback(config)

        dialog = BehaviorConfigDialog(self.root, on_save=on_save, initial_config=initial_config)
        self.root.wait_window(dialog.window)
        
    def _on_export_settings_click(self):
        """导出设置按钮点击"""
        from gui.export_settings_dialog import ExportSettingsDialog
        dialog = ExportSettingsDialog(self.root)
        self.root.wait_window(dialog.window)

    def set_callbacks(self, on_start=None, on_stop=None, on_pause=None, on_resume=None,
                     on_export=None, on_behavior_config=None):
        """
        设置回调函数

        Args:
            on_start: 开始录音回调
            on_stop: 停止录音回调
            on_pause: 暂停录音回调
            on_resume: 恢复录音回调
            on_export: 导出文档回调
            on_behavior_config: 行为配置回调
        """
        self.on_start_callback = on_start
        self.on_stop_callback = on_stop
        self.on_pause_callback = on_pause
        self.on_resume_callback = on_resume
        self.on_export_callback = on_export
        self.on_behavior_config_callback = on_behavior_config
        
    def update_transcription(self, text: str, append: bool = False):
        """
        更新转录文本显示

        Args:
            text: 要显示的文本
            append: 是否追加到现有文本
        """
        self.transcription_text.configure(state="normal")

        if append:
            self.transcription_text.insert("end", text)
        else:
            self.transcription_text.delete("0.0", "end")
            self.transcription_text.insert("0.0", text)
            # 清空搜索状态
            self._clear_search()

        self.transcription_text.configure(state="disabled")

        # 滚动锁定未勾选时才自动滚动到底部
        if not self.scroll_lock_var.get():
            self.transcription_text.see("end")

    def _clear_search(self):
        self.search_entry.delete(0, 'end')
        self.workspace.search()

    def _do_search(self):
        self.workspace.search()

    def _search_next(self):
        self.workspace.search_next()

    def _search_prev(self):
        self.workspace.search_next(-1)

    def _on_search_enter(self, event):
        self.workspace.search_next()

    def _on_search_key(self, event):
        self.workspace._schedule_search(event)

    def is_scroll_lock_enabled(self) -> bool:
        """获取是否启用滚动锁定

        Returns:
            True 表示锁定，False 表示自动滚动
        """
        return self.scroll_lock_var.get()
        
    def update_status(self, text: str):
        """
        更新状态栏文本
        
        Args:
            text: 状态文本
        """
        self.status_label.configure(text=text)
        
    def update_duration(self, seconds: int):
        """
        更新录音时长显示

        Args:
            seconds: 秒数
        """
        minutes = seconds // 60
        secs = seconds % 60
        self.duration_label.configure(text=f"{minutes:02d}:{secs:02d}")

    def update_volume(self, volume: float):
        """
        更新音量指示器

        Args:
            volume: 归一化音量 0.0-1.0
        """
        self.volume_bar.set(volume)

    def set_recording_indicator(self, is_recording: bool):
        """
        设置录音状态指示器

        Args:
            is_recording: 是否正在录音
        """
        if is_recording:
            if not self._is_recording_flashing:
                self._is_recording_flashing = True
                self._flash_recording_indicator()
        else:
            self._is_recording_flashing = False
            if self._recording_indicator_timer_id:
                self.root.after_cancel(self._recording_indicator_timer_id)
                self._recording_indicator_timer_id = None
            self.recording_indicator.configure(text_color=AppColors.RECORDING_INDICATOR_OFF)

    def _flash_recording_indicator(self):
        """闪烁录音指示灯（脉冲效果）"""
        self._recording_indicator_timer_id = None
        if not self._is_recording_flashing:
            return

        # 切换颜色
        current_color = self.recording_indicator.cget("text_color")
        if current_color == "red" or current_color == "#ff0000":
            self.recording_indicator.configure(text_color="#ff6666")
        else:
            self.recording_indicator.configure(text_color="red")

        # 500ms 后再次切换
        self._recording_indicator_timer_id = self.root.after(500, self._flash_recording_indicator)

    def get_selected_style(self) -> str:
        """获取当前选中的格式化风格

        Returns:
            风格名称字符串
        """
        return self.STYLE_LABELS.get(self.style_var.get(), self.style_var.get())

    def get_selected_device_index(self) -> Optional[int]:
        """获取当前选中的音频设备索引

        Returns:
            设备索引，如果使用默认设备则返回 None
        """
        return self.selected_device_index

    def get_save_audio(self) -> bool:
        """获取是否保存原始音频选项

        Returns:
            True 表示保存，False 表示不保存
        """
        return self.save_audio_var.get()

    def get_enable_llm_paragraphs(self) -> bool:
        """获取是否启用LLM语义分段选项

        Returns:
            True 表示启用，False 表示不启用
        """
        return self.llm_para_var.get()

    def get_asr_language(self) -> str:
        """获取当前选择的识别语言代码

        Returns:
            语言代码 (zh, en, yue 等)
        """
        choice = self.language_var.get()
        # 从显示文本提取语言代码 ("zh - 中文" -> "zh"
        lang_code = choice.split()[0]
        return lang_code

    def get_vad_silence_ms(self) -> int:
        """获取当前设置的VAD静音检测时长

        Returns:
            静音时长(毫秒)
        """
        return self.vad_silence_var.get()

    def run(self):
        """运行主循环"""
        self.root.mainloop()
        
    def close(self):
        """关闭窗口"""
        self.root.destroy()

    def _load_user_config(self) -> dict:
        """
        加载保存的用户配置

        Returns:
            配置字典，包含所有用户偏好
        """
        from config.settings import settings
        default_config = {
            "appearance_mode": "System",
            "font_size": 16,
            "asr_language": settings.asr.language,
            "vad_silence_ms": settings.asr.vad_silence_ms
        }

        if not self.USER_CONFIG_FILE.exists():
            return default_config

        try:
            with open(self.USER_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 合并默认值，确保新增配置有默认值
            merged = default_config.copy()
            merged.update(config)
            # 验证主题模式有效性
            if merged.get("appearance_mode") not in ["System", "Light", "Dark"]:
                merged["appearance_mode"] = default_config["appearance_mode"]
            # 验证字体大小有效性
            font_size = merged.get("font_size")
            if not isinstance(font_size, int) or font_size < 16 or font_size > 24:
                merged["font_size"] = default_config["font_size"]
            # 验证VAD静音时长范围
            vad_ms = merged.get("vad_silence_ms")
            if not isinstance(vad_ms, int) or vad_ms < 200 or vad_ms > 2000:
                merged["vad_silence_ms"] = default_config["vad_silence_ms"]
            logger.debug(f"加载用户配置: {merged}")
            return merged
        except Exception as e:
            logger.warning(f"加载用户配置失败，使用默认: {e}")
            return default_config

    def _save_user_config(self) -> None:
        """
        保存所有用户配置到配置文件
        """
        try:
            config = {}
            if self.USER_CONFIG_FILE.exists():
                with open(self.USER_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)

            config["appearance_mode"] = self.appearance_mode.get()
            config["font_size"] = self.font_size.get()
            config["asr_language"] = self.get_asr_language()
            config["vad_silence_ms"] = self.get_vad_silence_ms()

            with open(self.USER_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            logger.debug(f"保存用户配置: {config}")
        except Exception as e:
            logger.warning(f"保存用户配置失败: {e}")

    def _on_theme_change(self, mode: str) -> None:
        """
        主题模式切换回调

        Args:
            mode: 新的模式名称
        """
        # 应用主题
        ctk.set_appearance_mode(mode)
        self.workspace.refresh_theme()
        # 保存用户选择
        self._save_user_config()
        logger.info(f"主题已切换: {mode}")

    def _on_font_size_change(self, size_str: str) -> None:
        """
        字体大小改变回调

        Args:
            size_str: 选择的字体大小字符串
        """
        size = int(size_str)
        # 更新文本框字体（保持平台自适应字体族一致）
        self.workspace.set_font_size(size)
        self.transcription_text.configure(font=ctk.CTkFont(AppFonts.FAMILY, size))
        # 保存配置
        self._save_user_config()
        logger.info(f"文本字体已调整: {size}pt")

    def _show_help(self) -> None:
        """显示使用帮助对话框"""
        help_window = ctk.CTkToplevel(self.root)
        help_window.title("使用帮助 - 语音实时转录系统")
        help_window.geometry("750x600")
        help_window.resizable(True, True)
        help_window.transient(self.root)
        help_window.grab_set()

        help_text = """快速开始
────────────────────────────────
1. 打开右上角「设置」，选择麦克风、识别语言、VAD 和整理风格
2. 在「配置关键行为」中定义行为名称、描述和示例（可选）
3. 点击「开始录音」；录音中可暂停或继续
4. 点击「结束录音」，等待 AI 整理完成
5. 在「整理稿」中修订，用「对照」核查变化
6. 点击「保存修订」保留版本，或直接「导出文稿」
7. 在「会话历史」中搜索并重新打开本地记录

工作台按钮
────────────────────────────────
开始录音 / 暂停 / 结束录音：控制当前录音会话
导出文稿：导出当前整理稿；原始会话和音频仍保留
保存标题：保存会话标题，便于历史检索
保存修订：把当前整理稿保存为可恢复版本
撤销 / 重做：编辑整理稿时回退或恢复操作
重新整理：按当前风格和配置重新生成；输入未变化时复用上次行为分析
重新分析：忽略上次行为分析，强制重新调用模型；用于主动获取新结果
取消整理：中止正在进行的 AI 整理；已发送的请求可能仍需等待结束
回到最新：转录滚动锁定后，快速回到最新内容
播放 / 停止：回放已保存的原始音频；无音频时仅可查看文字
片段 / 分析 / 版本：查看句级片段、行为引文依据和历史整理稿
会话历史：按标题或原文搜索本地会话

重新整理与重新分析
────────────────────────────────
• 原文、行为配置、模型和提示词版本均未变化时，「重新整理」复用上次分析，结果稳定且不重复消耗 Token
• 修改行为定义、模型、AI 分段或分块设置后，「重新整理」会自动重新分析
• 「重新分析」始终重新调用模型；同一文本的结果可能有差异，这是 LLM 判定的正常随机性
• 人工修改整理稿不会改变行为分析依据；需要更新分析时请重新整理或重新分析

录音时长与稳定性
────────────────────────────────
• 单次实时识别会话的服务端上限约 30 分钟；应用会在约 20 分钟且检测到至少 2 秒静音时自动轮替会话
• 长时间连续说话可能接近 30 分钟上限；建议在 20 分钟左右停顿 2-3 秒，让应用安全轮替
• 应用没有总时长硬上限，但长时间录音依赖磁盘空间和稳定网络；16kHz 单声道 WAV 约 115MB/小时
• 网络中断时应用会自动重连；已确认的文本会保留，未发送的音频可能形成缺口
• 启用「保存原始音频」后才能回听和保留 WAV；关闭后仅保留文本

快捷键
────────────────────────────────
空格        → 未开始则开始；录音中暂停；暂停中继续
Esc         → 直接结束录音
Ctrl+S      → 导出文档
Ctrl+B      → 打开行为配置（macOS 可用 Command+B）
Ctrl+F / F3 → 搜索当前文稿
F5          → 刷新音频设备列表

VAD 参数
────────────────────────────────
VAD（语音活动检测）静音时长控制断句灵敏度：
• 200-500ms   → 灵敏断句，适合对话、访谈
• 500-1000ms  → 平衡模式，适合一般场景
• 1000-2000ms → 稳定断句，适合朗读、演讲

行为分析
────────────────────────────────
1. 支持 4-7 个自定义行为，内置会议、面试、心理咨询等模板
2. 行为描述和示例越具体，模型判定越稳定
3. 可启用 AI 语义分段和自动分块，提升长文本分析质量
4. 分析结果在正文原位标记，并在文末生成行为频率统计表
5. 频次表示模型识别且可在原文中定位的引文数量，不等同于绝对行为次数
6. 统计表会显示分析模型、分析时间，并提示 LLM 判定存在随机性

常用提示
────────────────────────────────
• 暂停录音：录音中点击「暂停」或按空格，可暂停后继续
• 滚动锁定：向上滚动后暂停跟随，点击「回到最新」继续跟随
• 主题切换：在底部状态栏选择浅色/深色/跟随系统
• 字体大小：在设置中调整转录文本显示字号
• 意外退出：重新启动会提示恢复最近保存的会话
• 隐私：API Key 保存在本机 .env；默认日志不记录完整转写内容

导出
────────────────────────────────
• Markdown (*.md) - 适合阅读和分享，保留行为标记
• Word (*.docx) - 适合正式文档和打印
• JSON (*.json) - 保留完整元数据、片段和行为匹配结果
"""

        # 创建文本框显示帮助
        text_frame = ctk.CTkFrame(help_window)
        text_frame.pack(padx=10, pady=10, fill="both", expand=True)

        help_textbox = ctk.CTkTextbox(
            text_frame,
            wrap="word",
            font=ctk.CTkFont(family=AppFonts.FAMILY, size=14)
        )
        help_textbox.pack(padx=10, pady=10, fill="both", expand=True)

        help_textbox.insert("0.0", help_text.strip())
        help_textbox.configure(state="disabled")

        # 关闭按钮
        close_btn = ctk.CTkButton(
            help_window,
            text="关闭",
            command=help_window.destroy,
            width=100,
            height=36
        )
        close_btn.pack(pady=(0, 10))

        # 居中窗口
        help_window.update_idletasks()
        width = help_window.winfo_width()
        height = help_window.winfo_height()
        x = (help_window.winfo_screenwidth() // 2) - (width // 2)
        y = (help_window.winfo_screenheight() // 2) - (height // 2)
        help_window.geometry(f"+{x}+{y}")

        logger.info("打开使用帮助")

    def _open_api_settings(self) -> None:
        """打开 API Key 设置对话框"""
        from gui.api_settings_dialog import APISettingsDialog
        from config.settings import settings

        dialog = APISettingsDialog(
            self.root,
            initial_dashscope=settings.api.dashscope_api_key,
            initial_bailian=settings.api.bailian_api_key,
            initial_region=settings.api.dashscope_region,
            initial_workspace=settings.api.dashscope_workspace_id,
            initial_proxy_mode=settings.api.proxy_mode,
            initial_proxy_url=settings.api.proxy_url,
            is_first_launch=False
        )
        self.root.wait_window(dialog.window)

        logger.info("API 设置对话框已关闭")


def main():
    """主函数"""
    app = MainWindow()
    
    # 设置回调示例
    def on_start():
        print("开始录音")
        
    def on_stop():
        print("停止录音")
        
    def on_export():
        print("导出文档")
        
    app.set_callbacks(on_start, on_stop, on_export)
    
    # 运行应用
    app.run()


if __name__ == "__main__":
    main()
