"""
语音实时转录系统 - 主应用程序

集成实时转录、格式化、GUI 的完整应用程序。
"""

import sys
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

import customtkinter as ctk
from loguru import logger

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import settings
from gui.main_window import MainWindow
from gui.export_dialog import ExportDialog
from gui.behavior_config_dialog import BehaviorConfigDialog
from core.realtime_transcriber import RealtimeTranscriber
from core.formatter.base import FormattedDocument, FormattingStyle, BehaviorMatch
from core.formatter.styles import RawStyle, CleanedStyle, ParagraphStyle, BehaviorMatchStyle
from core.formatter.behavior_matcher import BehaviorConfig, BehaviorDefinition


class VoiceTranscriptionApp:
    """
    语音实时转录应用程序
    
    集成实时转录、格式化、GUI 的完整应用。
    """
    
    def __init__(self):
        """初始化应用程序"""
        # 配置日志
        logger.remove()
        logger.add(sys.stderr, level="INFO")
        logger.add(
            project_root / "logs" / "app_{time:YYYY-MM-DD}.log",
            rotation="1 day",
            retention="7 days",
            level="DEBUG"
        )
        
        # 创建日志目录
        (project_root / "logs").mkdir(exist_ok=True)
        (project_root / "output").mkdir(exist_ok=True)
        
        # 应用程序状态
        self.is_recording = False
        self.current_document: Optional[FormattedDocument] = None
        self.behavior_config: Optional[BehaviorConfig] = None

        # 实时显示状态：分离已确认文本和当前中间结果
        self.confirmed_text = ""      # 已确认完成的文本
        self.current_partial = ""     # 当前正在识别的中间结果
        
        # 创建主窗口
        self.main_window = MainWindow()
        self._setup_callbacks()
        
        logger.info("应用程序初始化完成")
        
    def _setup_callbacks(self):
        """设置 GUI 回调函数"""
        # 重新绑定行为配置按钮，传递当前配置
        self.main_window.behavior_btn.configure(
            command=self._open_behavior_config
        )
        self.main_window.set_callbacks(
            on_start=self._on_start_recording,
            on_stop=self._on_stop_recording,
            on_export=self._on_export_document,
            on_behavior_config=self._on_behavior_config
        )
        
    def _on_start_recording(self):
        """开始录音回调"""
        logger.info("开始录音")
        self.is_recording = True

        # 开始录音前检查：如果选择了 behavior_match 但未配置行为，提示用户确认
        current_style = self.main_window.style_var.get()
        if current_style == "behavior_match":
            if not self.behavior_config or not self.behavior_config.behaviors:
                import tkinter.messagebox as messagebox
                result = messagebox.askyesno(
                    "关键行为未配置",
                    "当前选择的是「行为匹配」格式化风格，但尚未配置关键行为定义。\n\n行为匹配需要您先定义要识别的关键行为才能调用百炼 LLM 进行分析。\n\n是否现在打开配置界面？"
                )
                if result:
                    self._open_behavior_config()

        # 重置状态
        self.confirmed_text = ""
        self.current_partial = ""

        # 创建新文档
        self.current_document = FormattedDocument(
            title=f"录音_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            raw_text="",
            style=FormattingStyle.RAW,
            session_id=f"session_{datetime.now().timestamp()}",
            created_at=datetime.now()
        )

        # 更新 UI
        self.main_window.update_status("正在录音...")
        self.main_window.transcription_text.configure(state="normal")
        self.main_window.transcription_text.delete("0.0", "end")
        self.main_window.transcription_text.insert("0.0", "开始录音...\n\n")
        self.main_window.transcription_text.configure(state="disabled")
        
        # 启动实时转录线程
        try:
            # 使用配置的API Key
            api_key = settings.api.dashscope_api_key if settings.api.dashscope_api_key else None
            # 获取保存音频选项
            save_audio = self.main_window.get_save_audio()
            # 创建转录器
            self.transcriber = RealtimeTranscriber(
                api_key=api_key,
                save_audio=save_audio
            )

            def on_text(text, is_final):
                # 数据累积必须同步完成！否则 stop 时会读到旧数据（因为 after 异步排队）
                # GUI 更新放到 after 异步执行
                self._update_transcription_data(text, is_final)
                self.main_window.root.after(0, lambda: self._update_gui_display())

            # 获取选中的音频设备索引
            device_index = self.main_window.get_selected_device_index()
            if device_index is not None:
                logger.debug(f"使用选中的音频设备，索引: {device_index}")

            self.transcriber.start(on_text=on_text, device_index=device_index)
        except Exception as e:
            logger.error(f"启动实时转录失败: {e}")
            threading.Thread(target=self._mock_recording, daemon=True).start()
        
    def _mock_recording(self):
        """模拟录音过程（用于测试）"""
        import time
        
        texts = [
            "大家好，今天我们讨论一下项目进度。",
            "我觉得目前的进展还不错，",
            "但是还有一些问题需要解决。",
            "谁能说一下具体的困难？"
        ]
        
        for i, text in enumerate(texts):
            time.sleep(2)
            if not self.is_recording:
                break
                
            # 在 UI 线程中更新
            self.main_window.root.after(0, lambda t=text: self._append_transcription(t))
            
    def _update_transcription_data(self, text: str, is_final: bool = True):
        """
        更新转录数据（线程安全，同步执行）

        正确处理中间结果和最终结果：
        - 中间结果: 替换当前显示，不追加到文档
        - 最终结果: 追加到已确认文本，清空中间结果
        """
        if is_final:
            # 最终结果：追加到已确认文本
            if self.current_document:
                self.confirmed_text += text + " "
                self.current_document.raw_text = self.confirmed_text
            self.current_partial = ""
        else:
            # 中间结果：替换当前中间结果（DashScope每次返回完整句子，不是增量）
            self.current_partial = text

    def _update_gui_display(self):
        """更新 GUI 显示（在主线程执行）"""
        # 更新 UI 显示
        full_display = self.confirmed_text + self.current_partial

        self.main_window.transcription_text.configure(state="normal")
        self.main_window.transcription_text.delete("0.0", "end")
        self.main_window.transcription_text.insert("0.0", full_display)
        self.main_window.transcription_text.configure(state="disabled")
        self.main_window.transcription_text.see("end")

    def _append_transcription(self, text: str, is_final: bool = True):
        """
        兼容旧接口：更新转录文本
        保留这个方法是为了兼容，新代码使用 _update_transcription_data + _update_gui_display
        """
        self._update_transcription_data(text, is_final)
        self._update_gui_display()
        
    def _on_stop_recording(self):
        """停止录音回调"""
        logger.info("停止录音")
        self.is_recording = False

        # 停止转录器并获取最终完整文本
        if hasattr(self, 'transcriber') and self.transcriber and self.current_document:
            full_text = self.transcriber.stop()
            # 获取录音时长（总是设置，不管文本是否为空）
            duration = self.transcriber.get_duration()
            # 使用实际音频数据计算的更准确时长
            actual_duration = self.transcriber.get_audio_duration()
            self.current_document.duration_seconds = actual_duration

            # 双保险：App层实时累积一定是完整的，优先使用 App层累积
            # 因为每一次识别结果回调都会实时更新到 App层，不可能丢失
            # transcriber 汇总用作兜底，防止累积不一致
            # 无论如何，都要加上当前未确认的中间结果（一句话没说完就停止了），避免丢文本
            total_text = self.confirmed_text + self.current_partial
            total_text = total_text.strip()

            # 如果 App层累积为空，但 transcriber 有内容，使用 transcriber 的（兜底）
            if not total_text and full_text.strip():
                total_text = (full_text + " " + self.current_partial).strip()
                logger.info(f"转录完成(兜底使用ASR汇总): 字数 {len(total_text)}, 时长 {actual_duration:.1f}秒")
            else:
                logger.info(f"转录完成(使用App层实时累积): 字数 {len(total_text)}, 时长 {actual_duration:.1f}秒")

            self.current_document.raw_text = total_text

            # 自动保存原始录音 WAV 文件到默认输出目录
            from config.settings import settings
            output_dir = Path(settings.document.output_dir)
            if self.current_document.title and output_dir:
                wav_path = output_dir / f"{self.current_document.title}.wav"
                try:
                    self.transcriber.save_audio_wav(wav_path)
                    logger.info(f"原始录音已自动保存: {wav_path}")
                except Exception as e:
                    logger.error(f"保存原始录音失败: {e}")

        # 格式化文档
        if self.current_document:
            self._format_document()

        # 更新 UI
        self.main_window.update_status("录音已停止")
        self.main_window.transcription_text.configure(state="normal")
        self.main_window.transcription_text.insert("end", "\n\n录音结束。")
        self.main_window.transcription_text.configure(state="disabled")

        # 询问是否导出
        self._prompt_export()
        
    def _format_document(self):
        """格式化当前文档"""
        if not self.current_document:
            return

        # 根据选择的风格进行格式化
        style = self.main_window.style_var.get()

        if style == "cleaned":
            formatter = CleanedStyle()
        elif style == "paragraphs":
            # 获取LLM分段选项
            enable_llm = self.main_window.get_enable_llm_paragraphs()
            formatter = ParagraphStyle(enable_llm_reorganization=enable_llm)
        elif style == "behavior_match":
            if self.behavior_config and self.behavior_config.behaviors:
                # 已有配置，直接使用
                formatter = BehaviorMatchStyle(self.behavior_config)
            else:
                # 用户选择了 behavior_match 但未配置行为，提示并打开配置对话框
                import tkinter.messagebox as messagebox
                result = messagebox.askyesno(
                    "需要配置关键行为",
                    "行为匹配模式需要您定义要识别的关键行为。\n\n是否现在打开配置界面？"
                )
                if result:
                    # 打开配置对话框
                    self._open_behavior_config()
                    # 配置完成后，无论是否有行为都使用 BehaviorMatchStyle
                    # 如果用户配置了行为，使用用户配置；如果用户取消仍保持空配置
                    formatter = BehaviorMatchStyle(self.behavior_config)
                else:
                    # 用户取消配置，仍然使用 BehaviorMatchStyle（空配置）
                    # 创建默认空配置，保持行为匹配流程（会调用百炼 LLM）
                    if not self.behavior_config:
                        from core.formatter.behavior_matcher import BehaviorConfig
                        self.behavior_config = BehaviorConfig()
                    formatter = BehaviorMatchStyle(self.behavior_config)
        else:
            # raw 风格，不做处理
            formatter = RawStyle()

        # 对于 behavior_match 模式，需要调用 LLM 处理，可能耗时较长
        # 如果 paragraphs 启用了 LLM 分段，也需要调用 LLM，显示处理提示
        processing_window = None
        need_llm_processing = (
            (style == "behavior_match" and self.behavior_config and self.behavior_config.behaviors) or
            (style == "paragraphs" and self.main_window.get_enable_llm_paragraphs())
        )
        if need_llm_processing:
            processing_window = self._show_processing_window()

        try:
            # 执行格式化
            self.current_document = formatter.format(self.current_document)
        finally:
            # 无论如何都关闭处理中弹窗
            if processing_window:
                processing_window.destroy()

        # 更新显示
        if self.current_document.formatted_text:
            self.main_window.transcription_text.configure(state="normal")
            self.main_window.transcription_text.delete("0.0", "end")
            self.main_window.transcription_text.insert("0.0", self.current_document.formatted_text)
            self.main_window.transcription_text.configure(state="disabled")
            
    def _prompt_export(self):
        """提示导出文档"""
        if not self.current_document:
            return
            
        import tkinter.messagebox as messagebox
        
        if messagebox.askyesno(
            "导出文档",
            "录音已完成，是否导出文档？"
        ):
            self._on_export_document()
            
    def _on_export_document(self):
        """导出文档回调"""
        if not self.current_document:
            import tkinter.messagebox as messagebox
            messagebox.showwarning(
                "无法导出",
                "没有可导出的文档，请先进行录音。"
            )
            return
            
        # 打开导出对话框
        dialog = ExportDialog(
            self.main_window.root,
            self.current_document,
            on_export=self._on_export_complete
        )
        
    def _on_export_complete(self, file_path: Path):
        """
        导出完成回调

        Args:
            file_path: 导出的文件路径
        """
        logger.info(f"文档已导出: {file_path}")
        self.main_window.update_status(f"文档已导出: {file_path.name}")

    def _open_behavior_config(self):
        """打开行为配置对话框"""
        self.main_window._on_behavior_config_click(initial_config=self.behavior_config)

    def _on_behavior_config(self, config: BehaviorConfig):
        """行为配置保存回调"""
        self.behavior_config = config
        logger.info(f"关键行为配置已更新: {len(config.behaviors)} 个行为")
        self.main_window.update_status(f"关键行为配置已保存: {len(config.behaviors)} 个行为")

    def _show_processing_window(self):
        """显示处理中提示窗口（需要调用 LLM 处理，耗时较长）"""
        import customtkinter as ctk
        # 创建顶级窗口
        window = ctk.CTkToplevel(self.main_window.root)
        window.title("处理中")
        window.geometry("380x120")
        window.resizable(False, False)

        # 模态显示
        window.transient(self.main_window.root)
        # 不 grab_set，保持后台可以运行

        # 提示文本
        label = ctk.CTkLabel(
            window,
            text="正在调用大语言模型处理文本...\n这需要几秒钟到一分钟，请稍候...",
            font=ctk.CTkFont(size=14),
            justify="center"
        )
        label.pack(expand=True, padx=20, pady=20)

        # 更新 GUI 确保窗口显示
        window.update()

        logger.info("behavior_match 模式开始处理，显示处理中提示")
        return window

    def run(self):
        """运行应用程序"""
        logger.info("应用程序启动")
        self.main_window.run()
        logger.info("应用程序关闭")
        

if __name__ == "__main__":
    app = VoiceTranscriptionApp()
    app.run()
