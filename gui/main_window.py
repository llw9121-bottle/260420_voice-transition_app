"""
主窗口模块

提供基于 CustomTkinter 的主应用程序窗口。
"""

import customtkinter as ctk
from typing import Optional, Callable

from config.settings import settings
from core.formatter.base import FormattedDocument, FormattingStyle
from utils.logger import logger


class MainWindow:
    """
    主窗口类
    
    创建和管理应用程序的主界面。
    """
    
    def __init__(self):
        """初始化主窗口"""
        # 设置 CustomTkinter 外观
        ctk.set_appearance_mode("System")  # System, Dark, Light
        ctk.set_default_color_theme("blue")  # blue, green, dark-blue

        # 创建主窗口
        self.root = ctk.CTk()
        self.root.title("语音实时转录系统")
        self.root.geometry("1200x800")
        self.root.minsize(800, 600)

        # 存储回调函数
        self.on_start_callback: Optional[Callable] = None
        self.on_stop_callback: Optional[Callable] = None
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
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.title_label.pack(side="left", padx=10, pady=10)
        
        # 按钮框架
        self.button_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.button_frame.pack(side="right", padx=10, pady=10)
        
        # 开始按钮
        self.start_btn = ctk.CTkButton(
            self.button_frame,
            text="开始录音",
            command=self._on_start_click,
            width=120,
            height=35
        )
        self.start_btn.pack(side="left", padx=5)
        
        # 停止按钮
        self.stop_btn = ctk.CTkButton(
            self.button_frame,
            text="停止录音",
            command=self._on_stop_click,
            width=120,
            height=35,
            state="disabled"
        )
        self.stop_btn.pack(side="left", padx=5)
        
        # 导出按钮
        self.export_btn = ctk.CTkButton(
            self.button_frame,
            text="导出文档",
            command=self._on_export_click,
            width=120,
            height=35
        )
        self.export_btn.pack(side="left", padx=5)
        
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
        self.transcription_frame.grid_columnconfigure(0, weight=1)
        self.transcription_frame.grid_rowconfigure(1, weight=1)
        
        # 标签
        self.transcription_label = ctk.CTkLabel(
            self.transcription_frame,
            text="实时转录",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.transcription_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="w")
        
        # 文本框
        self.transcription_text = ctk.CTkTextbox(
            self.transcription_frame,
            wrap="word",
            font=ctk.CTkFont(size=12)
        )
        self.transcription_text.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="nsew")
        self.transcription_text.insert("0.0", "等待开始录音...")
        self.transcription_text.configure(state="disabled")
        
    def _create_settings_panel(self):
        """创建设置面板"""
        self.settings_frame = ctk.CTkFrame(self.content_frame)
        self.settings_frame.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")

        # 1. 格式化风格选择（最常用，放上方）
        self.style_label = ctk.CTkLabel(
            self.settings_frame,
            text="格式化风格",
            font=ctk.CTkFont(size=12, weight="bold")
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
            text="配置关键行为",
            command=self._on_behavior_config_click
        )
        self.behavior_btn.pack(fill="x", padx=10, pady=5)

        # 3. 导出设置按钮
        self.export_settings_btn = ctk.CTkButton(
            self.settings_frame,
            text="导出设置",
            command=self._on_export_settings_click
        )
        self.export_settings_btn.pack(fill="x", padx=10, pady=5)

        # 分隔线
        self.separator2 = ctk.CTkFrame(self.settings_frame, height=2, fg_color="gray30")
        self.separator2.pack(fill="x", padx=10, pady=10)

        # 4. 音频选项
        self.save_audio_label = ctk.CTkLabel(
            self.settings_frame,
            text="音频选项",
            font=ctk.CTkFont(size=12, weight="bold")
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

        # 5. 音频设备选择（不常用，放最底部）
        self.device_label = ctk.CTkLabel(
            self.settings_frame,
            text="音频输入设备",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.device_label.pack(anchor="w", padx=10, pady=(0, 5))

        self.device_var = ctk.StringVar(value="默认设备")
        self.device_menu = ctk.CTkOptionMenu(
            self.settings_frame,
            values=["加载中..."],
            variable=self.device_var,
            command=self._on_device_change,
            height=30
        )
        self.device_menu.pack(fill="x", padx=10, pady=(0, 5))

        # 刷新设备按钮 - 缩小高度让它更紧凑
        self.refresh_device_btn = ctk.CTkButton(
            self.settings_frame,
            text="刷新",
            command=self._refresh_devices,
            height=28
        )
        self.refresh_device_btn.pack(fill="x", padx=10, pady=(0, 10))

        # 存储设备列表
        self.available_devices: list[tuple[int, str]] = []  # (index, name)
        self.selected_device_index: Optional[int] = None
        
    def _create_status_bar(self):
        """创建底部状态栏"""
        self.status_frame = ctk.CTkFrame(self.main_frame, height=30)
        self.status_frame.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="ew")
        self.status_frame.grid_propagate(False)
        
        # 状态标签
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="就绪",
            font=ctk.CTkFont(size=11)
        )
        self.status_label.pack(side="left", padx=10)
        
        # 录音时长
        self.duration_label = ctk.CTkLabel(
            self.status_frame,
            text="00:00",
            font=ctk.CTkFont(size=11)
        )
        self.duration_label.pack(side="right", padx=10)
        
    # ===== 回调方法 =====
    
    def _on_start_click(self):
        """开始按钮点击"""
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_label.configure(text="正在录音...")
        
        if self.on_start_callback:
            self.on_start_callback()
            
    def _on_stop_click(self):
        """停止按钮点击"""
        self.stop_btn.configure(state="disabled")
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

    def _bind_shortcuts(self):
        """绑定键盘快捷键"""
        # 空格键: 开始/停止录音
        self.root.bind('<space>', self._on_space_shortcut)

    def _on_space_shortcut(self, event):
        """空格键快捷键处理"""
        # 如果焦点在文本框，不触发快捷键（允许输入空格）
        focused = self.root.focus_get()
        if focused and hasattr(focused, 'widget'):
            widget_name = str(focused.widget).lower()
            if 'text' in widget_name or 'entry' in widget_name:
                return  # 文本框聚焦时不拦截空格

        # 切换开始/停止状态
        if self.start_btn.cget('state') == 'normal':
            # 当前可以开始，点击开始
            self._on_start_click()
        elif self.stop_btn.cget('state') == 'normal':
            # 当前可以停止，点击停止
            self._on_stop_click()

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
    
    def set_callbacks(self, on_start=None, on_stop=None, on_export=None,
                     on_behavior_config=None):
        """
        设置回调函数

        Args:
            on_start: 开始录音回调
            on_stop: 停止录音回调
            on_export: 导出文档回调
            on_behavior_config: 行为配置回调
        """
        self.on_start_callback = on_start
        self.on_stop_callback = on_stop
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
            
        self.transcription_text.configure(state="disabled")
        self.transcription_text.see("end")
        
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

    def run(self):
        """运行主循环"""
        self.root.mainloop()
        
    def close(self):
        """关闭窗口"""
        self.root.destroy()


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
