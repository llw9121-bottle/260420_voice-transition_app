"""
主窗口模块

提供基于 CustomTkinter 的主应用程序窗口。
"""

import json
import sys
import customtkinter as ctk
from pathlib import Path
from typing import Optional, Callable

from config.settings import settings
from core.formatter.base import FormattedDocument, FormattingStyle
from utils.logger import logger

# 默认字体：Windows 使用微软雅黑，其他平台使用系统默认
if sys.platform.startswith('win'):
    DEFAULT_FONT_FAMILY = "Microsoft YaHei"
else:
    # macOS/Linux 使用系统默认字体
    DEFAULT_FONT_FAMILY = None


class MainWindow:
    """
    主窗口类
    
    创建和管理应用程序的主界面。
    """
    
    def __init__(self):
        """初始化主窗口"""
        # 配置文件路径（存储用户偏好）
        self.USER_CONFIG_FILE = Path(__file__).parent.parent / ".user_config.json"

        # 加载保存的用户偏好设置
        saved_config = self._load_user_config()
        saved_theme = saved_config.get("appearance_mode", "System")
        saved_font_size = saved_config.get("font_size", 16)

        # 设置 CustomTkinter 外观
        ctk.set_appearance_mode(saved_theme)
        ctk.set_default_color_theme("blue")  # blue, green, dark-blue

        # 创建主窗口（必须先创建 root 才能创建 StringVar）
        self.root = ctk.CTk()
        self.root.title("语音实时转录系统")
        self.root.geometry("1200x800")
        self.root.minsize(800, 600)

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

        # 启动后延迟刷新设备列表，避免卡顿
        self.root.after(100, self._refresh_devices)
        
    def _create_ui(self):
        """创建用户界面"""
        # 创建网格布局
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        
        # 主框架
        self.main_frame = ctk.CTkFrame(self.root)
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
        """创建顶部控制栏"""
        self.control_frame = ctk.CTkFrame(self.main_frame)
        self.control_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        
        # 标题
        self.title_label = ctk.CTkLabel(
            self.control_frame,
            text="语音实时转录系统",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=18, weight="bold")
        )
        self.title_label.pack(side="left", padx=10, pady=10)
        
        # 按钮框架
        self.button_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.button_frame.pack(side="right", padx=10, pady=10)
        
        # 开始按钮 - 绿色表示可开始（降低饱和度）
        self.start_btn = ctk.CTkButton(
            self.button_frame,
            text="▶ 开始录音",
            command=self._on_start_click,
            width=110,
            height=36,
            fg_color="#2D8855",
            hover_color="#1D6644"
        )
        self.start_btn.pack(side="left", padx=4)

        # 暂停/继续按钮 - 橙色表示暂停（降低饱和度）
        self.pause_btn = ctk.CTkButton(
            self.button_frame,
            text="⏸ 暂停",
            command=self._on_pause_click,
            width=90,
            height=36,
            state="disabled",
            fg_color="#AA7722",
            hover_color="#885511"
        )
        self.pause_btn.pack(side="left", padx=4)

        # 停止按钮 - 红色表示停止（降低饱和度）
        self.stop_btn = ctk.CTkButton(
            self.button_frame,
            text="⏹ 停止",
            command=self._on_stop_click,
            width=90,
            height=36,
            state="disabled",
            fg_color="#AA3333",
            hover_color="#882222"
        )
        self.stop_btn.pack(side="left", padx=4)

        # 导出按钮 - 蓝色表示操作（降低饱和度）
        self.export_btn = ctk.CTkButton(
            self.button_frame,
            text="💾 导出",
            command=self._on_export_click,
            width=80,
            height=36,
            fg_color="#335599",
            hover_color="#224477"
        )
        self.export_btn.pack(side="left", padx=4)
        
    def _create_content_area(self):
        """创建中间内容区"""
        self.content_frame = ctk.CTkFrame(self.main_frame)
        self.content_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=3)
        self.content_frame.grid_columnconfigure(1, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)
        
        # 左侧转录文本区
        self._create_transcription_area()
        
        # 右侧设置面板
        self._create_settings_panel()
        
    def _create_transcription_area(self):
        """创建转录文本区"""
        self.transcription_frame = ctk.CTkFrame(self.content_frame)
        self.transcription_frame.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")
        self.transcription_frame.grid_columnconfigure(1, weight=1)
        self.transcription_frame.grid_rowconfigure(1, weight=1)

        # 左侧标签
        self.transcription_label = ctk.CTkLabel(
            self.transcription_frame,
            text="📝 实时转录",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=14, weight="bold")
        )
        self.transcription_label.grid(row=0, column=0, padx=(12, 0), pady=(12, 6), sticky="w")

        # 中间搜索框区域
        self.search_frame = ctk.CTkFrame(self.transcription_frame, fg_color="transparent")
        self.search_frame.grid(row=0, column=1, padx=(10, 5), pady=(10, 5), sticky="ew")

        # 搜索输入框
        self.search_entry = ctk.CTkEntry(
            self.search_frame,
            placeholder_text="🔍 搜索...",
            width=140,
            height=30
        )
        self.search_entry.pack(side="left", padx=(0, 4))

        # 上一个匹配按钮
        self.prev_btn = ctk.CTkButton(
            self.search_frame,
            text="▲",
            command=self._search_prev,
            width=28,
            height=30,
            fg_color="#555555",
            hover_color="#333333"
        )
        self.prev_btn.pack(side="left", padx=(0, 2))

        # 下一个匹配按钮
        self.next_btn = ctk.CTkButton(
            self.search_frame,
            text="▼",
            command=self._search_next,
            width=28,
            height=30,
            fg_color="#555555",
            hover_color="#333333"
        )
        self.next_btn.pack(side="left", padx=(0, 4))

        # 字体大小标签
        self.font_size_label = ctk.CTkLabel(
            self.search_frame,
            text="🔤 字体:",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=11),
            text_color="gray"
        )
        self.font_size_label.pack(side="left", padx=(8, 2))

        # 字体大小选择下拉框
        self.font_size_menu = ctk.CTkOptionMenu(
            self.search_frame,
            values=["16", "18", "20", "22", "24"],
            variable=self.font_size,
            command=self._on_font_size_change,
            width=50,
            height=30,
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=10)
        )
        self.font_size_menu.pack(side="left", padx=(0, 0))

        # 右侧选项区域
        self.options_frame = ctk.CTkFrame(self.transcription_frame, fg_color="transparent")
        self.options_frame.grid(row=0, column=2, padx=(5, 12), pady=(10, 5), sticky="e")

        # 滚动锁定复选框 (Task 10)
        self.scroll_lock_var = ctk.BooleanVar(value=False)
        self.scroll_lock_check = ctk.CTkCheckBox(
            self.options_frame,
            text="🔒 滚动锁定",
            variable=self.scroll_lock_var,
            onvalue=True,
            offvalue=False,
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=11)
        )
        self.scroll_lock_check.pack(side="right")

        # 文本框（占据整行）
        self.transcription_text = ctk.CTkTextbox(
            self.transcription_frame,
            wrap="word",
            font=ctk.CTkFont(size=self.font_size.get())
        )
        self.transcription_text.grid(row=1, column=0, columnspan=3, padx=10, pady=(5, 10), sticky="nsew")
        self.transcription_text.insert("0.0", "等待开始录音...")
        self.transcription_text.configure(state="disabled")

        # 搜索状态
        self._search_matches: list[str] = []  # 存储所有匹配位置
        self._current_match_index: int = -1
        self._search_last_term: str = ""

        # 配置搜索高亮标签
        self.transcription_text.tag_config("search_highlight", background="#ffff00", foreground="#000000")
        self.transcription_text.tag_config("search_current", background="#ff8800", foreground="#000000")

        # 绑定搜索事件
        self.search_entry.bind("<Return>", self._on_search_enter)
        self.search_entry.bind("<KeyRelease>", self._on_search_key)
        
    def _create_settings_panel(self):
        """创建设置面板"""
        self.settings_frame = ctk.CTkFrame(self.content_frame)
        self.settings_frame.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")

        # 1. 格式化风格选择（最常用，放上方）
        self.style_label = ctk.CTkLabel(
            self.settings_frame,
            text="格式化风格",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=12, weight="bold")
        )
        self.style_label.pack(anchor="w", padx=10, pady=(10, 5))

        self.style_var = ctk.StringVar(value="cleaned")
        self.style_menu = ctk.CTkOptionMenu(
            self.settings_frame,
            values=["raw", "cleaned", "paragraphs", "behavior_match"],
            variable=self.style_var,
            command=self._on_style_change
        )
        self.style_menu.pack(fill="x", padx=10, pady=5)

        # 段落选项：LLM语义分段（仅paragraphs模式可用
        self.llm_para_var = ctk.BooleanVar(value=False)
        self.llm_para_check = ctk.CTkCheckBox(
            self.settings_frame,
            text="启用 LLM 语义分段（仅段落模式，消耗Token）",
            variable=self.llm_para_var,
            onvalue=True,
            offvalue=False
        )
        self.llm_para_check.pack(anchor="w", padx=10, pady=(0, 5))

        # 分隔线
        self.separator1 = ctk.CTkFrame(self.settings_frame, height=2, fg_color="gray30")
        self.separator1.pack(fill="x", padx=10, pady=10)

        # 2. 行为匹配配置按钮
        self.behavior_btn = ctk.CTkButton(
            self.settings_frame,
            text="⚙ 配置关键行为",
            command=self._on_behavior_config_click,
            height=36
        )
        self.behavior_btn.pack(fill="x", padx=10, pady=(0, 6))

        # 3. 导出设置按钮
        self.export_settings_btn = ctk.CTkButton(
            self.settings_frame,
            text="📝 导出设置",
            command=self._on_export_settings_click,
            height=36
        )
        self.export_settings_btn.pack(fill="x", padx=10, pady=(0, 6))

        # 分隔线
        self.separator2 = ctk.CTkFrame(self.settings_frame, height=2, fg_color="gray30")
        self.separator2.pack(fill="x", padx=10, pady=10)

        # 4. 音频选项
        self.save_audio_label = ctk.CTkLabel(
            self.settings_frame,
            text="音频选项",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=12, weight="bold")
        )
        self.save_audio_label.pack(anchor="w", padx=10, pady=(0, 5))

        self.save_audio_var = ctk.BooleanVar(value=True)
        self.save_audio_switch = ctk.CTkSwitch(
            self.settings_frame,
            text="保存原始音频(WAV)",
            variable=self.save_audio_var,
            onvalue=True,
            offvalue=False,
            command=self._on_save_audio_change
        )
        self.save_audio_switch.pack(anchor="w", padx=10, pady=(0, 10))

        # 分隔线
        self.separator3 = ctk.CTkFrame(self.settings_frame, height=2, fg_color="gray30")
        self.separator3.pack(fill="x", padx=10, pady=10)

        # 5. ASR 识别设置
        self.asr_label = ctk.CTkLabel(
            self.settings_frame,
            text="识别设置",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=12, weight="bold")
        )
        self.asr_label.pack(anchor="w", padx=10, pady=(0, 5))

        # 语言选择
        self.language_label = ctk.CTkLabel(
            self.settings_frame,
            text="识别语言:",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=11)
        )
        self.language_label.pack(anchor="w", padx=15, pady=(0, 3))

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
            self.settings_frame,
            values=language_options,
            variable=self.language_var,
            command=self._on_language_change,
            height=30,
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=11)
        )
        self.language_menu.pack(fill="x", padx=15, pady=(0, 8))

        # VAD 静音检测时长
        self.vad_label = ctk.CTkLabel(
            self.settings_frame,
            text=f"断句灵敏度: {self.saved_vad_ms} ms",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=11)
        )
        self.vad_label.pack(anchor="w", padx=15, pady=(0, 3))

        self.vad_silence_var = ctk.IntVar(value=self.saved_vad_ms)
        self.vad_slider = ctk.CTkSlider(
            self.settings_frame,
            from_=200,
            to=2000,
            number_of_steps=18,  # 200-2000 每步100
            variable=self.vad_silence_var,
            command=self._on_vad_change
        )
        self.vad_slider.pack(fill="x", padx=15, pady=(0, 3))

        self.vad_hint_label = ctk.CTkLabel(
            self.settings_frame,
            text="短=灵敏快断  长=稳定少断",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=9),
            text_color="gray"
        )
        self.vad_hint_label.pack(anchor="e", padx=15, pady=(0, 10))

        # 分隔线
        self.separator4 = ctk.CTkFrame(self.settings_frame, height=2, fg_color="gray30")
        self.separator4.pack(fill="x", padx=10, pady=10)

        # 6. 音频输入设备选择（不常用，放最底部）
        self.device_label = ctk.CTkLabel(
            self.settings_frame,
            text="音频输入设备",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=12, weight="bold")
        )
        self.device_label.pack(anchor="w", padx=10, pady=(0, 5))

        # 设备选择框架 - 下拉框和刷新按钮并排显示
        self.device_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.device_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.device_frame.grid_columnconfigure(0, weight=1)
        self.device_frame.grid_columnconfigure(1, weight=0)

        self.device_var = ctk.StringVar(value="默认设备")
        self.device_menu = ctk.CTkOptionMenu(
            self.device_frame,
            values=["加载中..."],
            variable=self.device_var,
            command=self._on_device_change,
            height=30
        )
        self.device_menu.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        # 刷新设备按钮
        self.refresh_device_btn = ctk.CTkButton(
            self.device_frame,
            text="刷新",
            command=self._refresh_devices,
            height=30,
            width=60
        )
        self.refresh_device_btn.grid(row=0, column=1, sticky="e")

        # 存储设备列表
        self.available_devices: list[tuple[int, str]] = []  # (index, name)
        self.selected_device_index: Optional[int] = None
        
    def _create_status_bar(self):
        """创建底部状态栏"""
        self.status_frame = ctk.CTkFrame(self.main_frame, height=34)
        self.status_frame.grid(row=2, column=0, padx=12, pady=(6, 10), sticky="ew")
        self.status_frame.grid_propagate(False)

        # 录音状态指示灯（最左侧）
        self.recording_indicator = ctk.CTkLabel(
            self.status_frame,
            text="●",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=18),
            text_color="gray50"
        )
        self.recording_indicator.pack(side="left", padx=(12, 0))

        # 状态标签
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="就绪",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=12)
        )
        self.status_label.pack(side="left", padx=10, pady=8)

        # 音量指示器框架（最右侧）
        self.volume_frame = ctk.CTkFrame(
            self.status_frame,
            width=80,
            height=18,
            fg_color="gray20"
        )
        self.volume_frame.pack(side="right", padx=(2, 12))
        self.volume_frame.grid_propagate(False)

        # 音量进度条
        self.volume_bar = ctk.CTkProgressBar(
            self.volume_frame,
            width=76,
            height=14,
            corner_radius=2
        )
        self.volume_bar.set(0)
        self.volume_bar.place(relx=0.5, rely=0.5, anchor="center")

        # 音量标签
        self.volume_label = ctk.CTkLabel(
            self.status_frame,
            text="音量:",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=11),
            text_color="gray"
        )
        self.volume_label.pack(side="right", padx=(5, 2))

        # 主题模式选择（音量左边）
        self.theme_menu = ctk.CTkOptionMenu(
            self.status_frame,
            values=["System", "Light", "Dark"],
            variable=self.appearance_mode,
            command=self._on_theme_change,
            width=80,
            height=22,
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=10)
        )
        self.theme_menu.pack(side="right", padx=(2, 5))

        self.theme_label = ctk.CTkLabel(
            self.status_frame,
            text="🎨 主题:",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=11),
            text_color="gray"
        )
        self.theme_label.pack(side="right", padx=(8, 2))

        # 时长标签
        self.duration_label = ctk.CTkLabel(
            self.status_frame,
            text=" ⏱  00:00",
            font=ctk.CTkFont(family=DEFAULT_FONT_FAMILY, size=12)
        )
        self.duration_label.pack(side="right", padx=(0, 8))

        # 闪烁动画控制
        self._is_recording_flashing = False
        
    # ===== 回调方法 =====
    
    def _on_start_click(self):
        """开始按钮点击"""
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal", text="暂停")
        self.stop_btn.configure(state="normal")
        self.status_label.configure(text="正在录音...")

        if self.on_start_callback:
            self.on_start_callback()

    def _on_pause_click(self):
        """暂停/继续按钮点击"""
        current_text = self.pause_btn.cget("text")

        if current_text == "暂停":
            # 切换到暂停状态
            self.pause_btn.configure(text="继续")
            self.status_label.configure(text="已暂停")
            if self.on_pause_callback:
                self.on_pause_callback()
        else:
            # 切换到继续状态
            self.pause_btn.configure(text="暂停")
            self.status_label.configure(text="正在录音...")
            if self.on_resume_callback:
                self.on_resume_callback()

    def _on_stop_click(self):
        """停止按钮点击"""
        self.stop_btn.configure(state="disabled")
        self.pause_btn.configure(state="disabled", text="暂停")
        self.start_btn.configure(state="normal")
        self.status_label.configure(text="录音已停止")

        if self.on_stop_callback:
            self.on_stop_callback()
            
    def _on_export_click(self):
        """导出按钮点击"""
        if self.on_export_callback:
            self.on_export_callback()
            
    def _on_style_change(self, choice):
        """格式化风格改变"""
        logger.info(f"格式化风格已更改为: {choice}")

        # 如果用户切换到 behavior_match 且尚未配置行为，提示打开配置界面
        if choice == "behavior_match" and self.on_behavior_config_callback is not None:
            import tkinter.messagebox as messagebox
            result = messagebox.askyesno(
                "配置关键行为",
                "您选择了「行为匹配」格式化风格。\n\n行为匹配需要您先定义要识别的关键行为。\n\n是否现在打开配置界面？"
            )
            if result:
                self._on_behavior_config_click()

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

    def _on_space_shortcut(self, event):
        """空格键快捷键处理"""
        # 如果焦点在文本框，不触发快捷键（允许输入空格）
        focused = self.root.focus_get()
        if focused and hasattr(focused, 'widget'):
            widget_name = str(focused.widget).lower()
            if 'text' in widget_name or 'entry' in widget_name:
                return  # 文本框聚焦时不拦截空格

        # 切换开始/停止/暂停状态
        if self.start_btn.cget('state') == 'normal':
            # 当前可以开始，点击开始
            self._on_start_click()
        elif self.pause_btn.cget('state') == 'normal':
            # 当前正在录音，可以暂停/继续
            self._on_pause_click()
        elif self.stop_btn.cget('state') == 'normal':
            # 当前可以停止，点击停止
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
        self._on_behavior_config_click()

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
        
    # ===== 公共方法 =====
    
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

    # ===== 搜索功能 (Task 7) =====

    def _clear_search(self):
        """清空搜索高亮和状态"""
        self.transcription_text.tag_remove("search_highlight", "0.0", "end")
        self.transcription_text.tag_remove("search_current", "0.0", "end")
        self._search_matches = []
        self._current_match_index = -1
        self._search_last_term = ""

    def _do_search(self):
        """执行搜索，高亮所有匹配项"""
        search_term = self.search_entry.get().strip()
        if not search_term:
            self._clear_search()
            return

        # 如果搜索词变化，重新搜索
        if search_term != self._search_last_term:
            self._clear_search()
            self._search_last_term = search_term

        # 获取全文内容
        content = self.transcription_text.get("0.0", "end-1c")
        if not content:
            return

        # 不区分大小写搜索
        content_lower = content.lower()
        term_lower = search_term.lower()
        term_len = len(search_term)

        # 查找所有匹配位置
        matches = []
        start = 0
        while True:
            pos = content_lower.find(term_lower, start)
            if pos < 0:
                break
            # 转换为 tkinter 位置格式 (line.char)
            line = content[:pos].count('\n')
            char = pos - content[:pos].rfind('\n') - 1
            start_pos = f"{line+1}.{char}"
            end_pos = f"{line+1}.{char + term_len}"
            matches.append((start_pos, end_pos))
            start = pos + 1

        # 高亮所有匹配项
        self.transcription_text.tag_remove("search_highlight", "0.0", "end")
        self.transcription_text.tag_remove("search_current", "0.0", "end")

        for start_pos, end_pos in matches:
            self.transcription_text.tag_add("search_highlight", start_pos, end_pos)

        self._search_matches = [start for start, _ in matches]

        if self._search_matches:
            self._current_match_index = 0
            self._highlight_current()
            self._goto_current()
            logger.debug(f"搜索完成，找到 {len(self._search_matches)} 个匹配项")
        else:
            logger.debug("未找到匹配项")

    def _highlight_current(self):
        """高亮当前匹配项"""
        self.transcription_text.tag_remove("search_current", "0.0", "end")
        if 0 <= self._current_match_index < len(self._search_matches):
            start_pos = self._search_matches[self._current_match_index]
            search_term = self.search_entry.get().strip()
            # 计算结束位置
            line_char = start_pos.split('.')
            line = int(line_char[0])
            char = int(line_char[1])
            end_pos = f"{line}.{char + len(search_term)}"
            self.transcription_text.tag_add("search_current", start_pos, end_pos)

    def _goto_current(self):
        """滚动到当前匹配项"""
        if 0 <= self._current_match_index < len(self._search_matches):
            pos = self._search_matches[self._current_match_index]
            self.transcription_text.see(pos)

    def _search_next(self):
        """搜索下一个匹配项"""
        if not self._search_matches:
            self._do_search()
            return
        if self._current_match_index < len(self._search_matches) - 1:
            self._current_match_index += 1
        else:
            self._current_match_index = 0  # 循环到开头
        self._highlight_current()
        self._goto_current()

    def _search_prev(self):
        """搜索上一个匹配项"""
        if not self._search_matches:
            self._do_search()
            return
        if self._current_match_index > 0:
            self._current_match_index -= 1
        else:
            self._current_match_index = len(self._search_matches) - 1  # 循环到末尾
        self._highlight_current()
        self._goto_current()

    def _on_search_enter(self, event):
        """回车键触发搜索下一个"""
        self._search_next()

    def _on_search_key(self, event):
        """按键释放时实时搜索"""
        # 延迟一点搜索，让输入更流畅
        self.transcription_text.after(100, self._do_search)

    # ===== 公共方法获取状态 =====

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
            self._is_recording_flashing = True
            self._flash_recording_indicator()
        else:
            self._is_recording_flashing = False
            self.recording_indicator.configure(text_color="gray50")

    def _flash_recording_indicator(self):
        """闪烁录音指示灯（脉冲效果）"""
        if not self._is_recording_flashing:
            return

        # 切换颜色
        current_color = self.recording_indicator.cget("text_color")
        if current_color == "red" or current_color == "#ff0000":
            self.recording_indicator.configure(text_color="#ff6666")
        else:
            self.recording_indicator.configure(text_color="red")

        # 500ms 后再次切换
        self.root.after(500, self._flash_recording_indicator)

    def get_selected_style(self) -> str:
        """获取当前选中的格式化风格

        Returns:
            风格名称字符串
        """
        return self.style_var.get()

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

    # ===== 用户配置持久化 =====

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
            # 读取现有配置如果存在
            config = {}
            if self.USER_CONFIG_FILE.exists():
                with open(self.USER_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)

            # 更新所有当前设置
            config["appearance_mode"] = self.appearance_mode.get()
            config["font_size"] = self.font_size.get()
            config["asr_language"] = self.get_asr_language()
            config["vad_silence_ms"] = self.get_vad_silence_ms()

            # 保存回去
            with open(self.USER_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            logger.debug(f"保存用户配置: {config}")
        except Exception as e:
            logger.warning(f"保存用户配置失败: {e}")

    # ===== 主题切换相关方法 =====

    def _on_theme_change(self, mode: str) -> None:
        """
        主题模式切换回调

        Args:
            mode: 新的模式名称
        """
        # 应用主题
        ctk.set_appearance_mode(mode)
        # 保存用户选择
        self._save_user_config()
        logger.info(f"主题已切换: {mode}")

    # ===== 字体大小调整 =====

    def _on_font_size_change(self, size_str: str) -> None:
        """
        字体大小改变回调

        Args:
            size_str: 选择的字体大小字符串
        """
        size = int(size_str)
        # 更新文本框字体
        self.transcription_text.configure(font=ctk.CTkFont(size=size))
        # 保存配置
        self._save_user_config()
        logger.info(f"文本字体已调整: {size}pt")


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
