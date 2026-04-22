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
        # 创建临时目录（用于自动保存未完成录音）
        self.tmp_dir = project_root / ".tmp"
        self.tmp_dir.mkdir(exist_ok=True)

        # 应用程序状态
        self.is_recording = False
        self.current_document: Optional[FormattedDocument] = None
        self.behavior_config: Optional[BehaviorConfig] = None

        # 实时显示状态：分离已确认文本和当前中间结果
        self.confirmed_text = ""      # 已确认完成的文本
        self.current_partial = ""     # 当前正在识别的中间结果

        # 自动保存临时文件配置
        self._auto_save_timer_id: Optional[str] = None
        self._current_tmp_file: Optional[Path] = None
        
        # 创建主窗口
        self.main_window = MainWindow()
        self._setup_callbacks()
        
        logger.info("应用程序初始化完成")

        # 检查API Key配置，未配置时弹出友好提示
        self._check_api_configuration_on_startup()

        # 检查是否有未完成的录音（上次崩溃遗留）
        self._check_unsaved_recording()
        
    def _setup_callbacks(self):
        """设置 GUI 回调函数"""
        # 重新绑定行为配置按钮，传递当前配置
        self.main_window.behavior_btn.configure(
            command=self._open_behavior_config
        )
        self.main_window.set_callbacks(
            on_start=self._on_start_recording,
            on_stop=self._on_stop_recording,
            on_pause=self._on_pause_recording,
            on_resume=self._on_resume_recording,
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
        # 获取 ASR 设置
        language = self.main_window.get_asr_language()
        vad_silence_ms = self.main_window.get_vad_silence_ms()

        self.current_document = FormattedDocument(
            title=f"录音_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            raw_text="",
            style=FormattingStyle.RAW,
            session_id=f"session_{datetime.now().timestamp()}",
            language=language,
            created_at=datetime.now()
        )

        # 更新 UI
        self.main_window.update_status("正在录音...")
        self.main_window.update_duration(0)
        self.main_window.set_recording_indicator(True)
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
                language=language,
                vad_silence_ms=vad_silence_ms,
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

            # 启动时长更新定时器（每秒更新一次）
            self._update_duration()

            # 启动自动保存（防崩溃）
            self._start_auto_save()
        except Exception as e:
            logger.error(f"启动实时转录失败: {e}")
            # 弹出错误提示给用户
            import tkinter.messagebox as messagebox
            error_msg = str(e)
            if "websocket connection could not established" in error_msg or "timeout" in error_msg.lower():
                messagebox.showerror(
                    "连接失败",
                    f"无法连接到阿里云 DashScope 服务（连接超时）。\n\n"
                    f"错误信息: {error_msg}\n\n"
                    f"可能原因：\n"
                    f"1. 网络无法访问阿里云，请检查网络连接\n"
                    f"2. 防火墙阻止了 WebSocket 连接\n"
                    f"3. API Key 无效或过期，请检查 .env 配置\n"
                    f"4. 阿里云服务暂时不可用，请稍后重试"
                )
            else:
                messagebox.showerror(
                    "启动失败",
                    f"启动实时转录失败。\n\n"
                    f"错误信息: {error_msg}\n\n"
                    f"请检查日志获取更多详细信息。"
                )
            # 重置UI状态
            self.main_window._on_stop_click()
            self.is_recording = False

    def _update_duration(self):
        """更新录音时长显示（定时器回调）"""
        if self.is_recording and hasattr(self, 'transcriber') and self.transcriber:
            duration = int(self.transcriber.get_duration())
            volume = self.transcriber.get_current_volume()
            self.main_window.update_duration(duration)
            self.main_window.update_volume(volume)
            # 1秒后再次更新
            self.main_window.root.after(1000, self._update_duration)

    def _on_pause_recording(self):
        """暂停录音回调"""
        logger.info("暂停录音")
        if hasattr(self, 'transcriber') and self.transcriber:
            self.transcriber.pause()
        self.is_recording = False  # 暂停时不再更新时长

    def _on_resume_recording(self):
        """恢复录音回调"""
        logger.info("恢复录音")
        if hasattr(self, 'transcriber') and self.transcriber:
            self.transcriber.resume()
        self.is_recording = True
        # 恢复时长更新定时器
        self._update_duration()
        
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

        # 停止自动保存
        self._stop_auto_save()

        # 停止转录器并获取最终完整文本
        if hasattr(self, 'transcriber') and self.transcriber and self.current_document:
            full_text = self.transcriber.stop()
            # 获取录音时长（总是设置，不管文本是否为空）
            duration = self.transcriber.get_duration()
            # 使用实际音频数据计算的更准确时长，如果为0（save_audio=False），使用基于时间的时长
            actual_duration = self.transcriber.get_audio_duration()
            if actual_duration <= 0 and duration > 0:
                actual_duration = duration
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
            # 仅在用户勾选了"保存原始音频"选项时才保存
            from config.settings import settings
            output_dir = Path(settings.document.output_dir)
            save_audio = self.main_window.get_save_audio()
            if save_audio and self.current_document.title and output_dir:
                wav_path = output_dir / f"{self.current_document.title}.wav"
                try:
                    self.transcriber.save_audio_wav(wav_path)
                    logger.info(f"原始录音已自动保存: {wav_path}")
                except Exception as e:
                    logger.error(f"保存原始录音失败: {e}")

        # 更新 UI
        self.main_window.update_status("录音已停止")
        self.main_window.update_volume(0)
        self.main_window.set_recording_indicator(False)
        self.main_window.transcription_text.configure(state="normal")
        self.main_window.transcription_text.insert("end", "\n\n录音结束。")
        self.main_window.transcription_text.configure(state="disabled")

        # 格式化文档
        if self.current_document:
            self._format_document()

        # 不需要LLM处理的情况：格式化已经完成，可以直接提示导出
        # 需要LLM处理的情况：会在格式化完成回调中提示导出
        style = self.main_window.get_selected_style()
        need_llm_processing = (
            (style == "behavior_match" and self.behavior_config and self.behavior_config.behaviors) or
            (style == "paragraphs" and self.main_window.get_enable_llm_paragraphs())
        )
        if not need_llm_processing:
            # 格式化已经完成，提示导出
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
        need_llm_processing = (
            (style == "behavior_match" and self.behavior_config and self.behavior_config.behaviors) or
            (style == "paragraphs" and self.main_window.get_enable_llm_paragraphs())
        )

        if need_llm_processing:
            # 显示处理中弹窗
            processing_window = self._show_processing_window()
            # 在后台线程执行格式化（避免阻塞主线程导致界面卡住）
            def format_in_background():
                try:
                    formatted_doc = formatter.format(self.current_document)
                    # 在主线程更新结果
                    self.main_window.root.after(0, lambda: self._on_format_complete(formatted_doc, processing_window))
                except Exception as e:
                    logger.error(f"格式化文档失败: {e}")
                    # 在主线程显示错误
                    self.main_window.root.after(0, lambda: self._on_format_error(e, processing_window))

            threading.Thread(target=format_in_background, daemon=True).start()
        else:
            # 不需要LLM处理，直接在主线程执行
            self.current_document = formatter.format(self.current_document)
            self._update_formatted_display()

    def _on_format_complete(self, formatted_doc: FormattedDocument, processing_window):
        """格式化完成回调（在主线程执行）"""
        self.current_document = formatted_doc
        # 关闭处理中弹窗
        if processing_window:
            processing_window.destroy()
        # 更新显示
        self._update_formatted_display()
        logger.info("文档格式化完成")
        # 格式化完成后提示导出
        self._prompt_export()

    def _on_format_error(self, error: Exception, processing_window):
        """格式化错误回调（在主线程执行）"""
        # 关闭处理中弹窗
        if processing_window:
            processing_window.destroy()
        # 显示错误
        import tkinter.messagebox as messagebox
        messagebox.showerror(
            "格式化失败",
            f"文档格式化过程中发生错误:\n\n{str(error)}\n\n请检查网络连接和 API Key 配置后重试。"
        )
        logger.error(f"格式化文档失败: {error}")

    def _update_formatted_display(self):
        """更新格式化后的文本显示"""
        if self.current_document and self.current_document.formatted_text:
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
        # 导出完成，清理临时文件
        self._stop_auto_save()
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

    def _check_api_configuration_on_startup(self):
        """
        启动时检查API配置，如果未配置弹出友好提示引导用户配置。
        """
        from config.settings import check_api_configuration
        status = check_api_configuration()

        if not status["dashscope_configured"]:
            # DashScope API Key 未配置，弹出提示
            def show_config_prompt():
                import tkinter.messagebox as messagebox
                result = messagebox.showwarning(
                    "API Key 未配置",
                    "检测到 DashScope API Key 尚未配置。\n\n"
                    "本应用需要阿里云 DashScope 服务进行实时语音识别，请按以下步骤配置：\n"
                    "1. 在项目根目录复制 .env.example 为 .env\n"
                    "2. 打开 .env 文件，填入你的 DASHSCOPE_API_KEY\n"
                    "3. 重启应用\n\n"
                    "获取 API Key: https://help.aliyun.com/zh/dashscope/developer-reference/acquisition-and-configuration-of-api-key\n\n"
                    "配置完成后重启应用即可开始使用。"
                )

            # 在主窗口加载后显示提示
            self.main_window.root.after(500, show_config_prompt)
            logger.warning("DashScope API Key 未配置，提示用户配置")

    def _check_unsaved_recording(self):
        """
        检查是否有未完成的录音（上次应用崩溃遗留），如果有提示用户恢复。
        """
        import json
        import glob
        from datetime import datetime

        # 查找所有临时文件
        tmp_files = list(self.tmp_dir.glob("unsaved_*.json"))

        if not tmp_files:
            # 没有未完成的录音
            return

        # 按修改时间排序，最新的在最后
        tmp_files.sort(key=lambda p: p.stat().st_mtime)
        latest_tmp = tmp_files[-1]

        # 读取创建时间
        try:
            with open(latest_tmp, 'r', encoding='utf-8') as f:
                data = json.load(f)
            create_time = datetime.fromtimestamp(latest_tmp.stat().st_mtime)
            time_str = create_time.strftime('%Y-%m-%d %H:%M:%S')
            text_length = len(data.get('confirmed_text', ''))

            def ask_recovery():
                import tkinter.messagebox as messagebox
                result = messagebox.askyesno(
                    "发现未完成的录音",
                    f"检测到上次应用退出时遗留了一个未完成的录音:\n\n"
                    f"创建时间: {time_str}\n"
                    f"文本长度: {text_length} 字\n\n"
                    f"是否恢复这个录音到编辑器？"
                )
                if result:
                    self._restore_unsaved_recording(data)
                    # 删除临时文件（恢复后不再需要）
                    try:
                        latest_tmp.unlink()
                    except Exception as e:
                        logger.debug(f"删除临时文件失败: {e}")

            # 在主窗口加载后询问用户
            self.main_window.root.after(800, ask_recovery)
            logger.info(f"发现未完成录音: {latest_tmp.name}，已提示用户恢复")

        except Exception as e:
            logger.warning(f"读取未完成录音失败: {e}")

    def _restore_unsaved_recording(self, data: dict):
        """
        恢复未完成的录音到编辑器。

        Args:
            data: 保存的临时数据
        """
        # 恢复文本内容
        self.confirmed_text = data.get('confirmed_text', '')
        self.current_partial = data.get('current_partial', '')

        # 创建文档对象
        from core.formatter.base import FormattedDocument, FormattingStyle
        from datetime import datetime

        self.current_document = FormattedDocument(
            title=data.get('title', '恢复的未完成录音'),
            raw_text=self.confirmed_text + self.current_partial,
            style=FormattingStyle.RAW,
            session_id=data.get('session_id', f'recovered_{datetime.now().timestamp()}'),
            created_at=datetime.now()
        )
        self.current_document.word_count = len(self.confirmed_text)

        # 更新显示
        self._update_gui_display()
        self.main_window.update_status("已恢复未完成的录音")
        logger.info(f"成功恢复未完成录音，字数: {len(self.confirmed_text)}")

    def _start_auto_save(self):
        """
        启动自动保存定时器，每隔 30 秒自动保存当前转录内容。
        """
        # 停止之前的定时器（如果有）
        self._stop_auto_save()

        # 创建新的临时文件
        timestamp = int(datetime.now().timestamp())
        self._current_tmp_file = self.tmp_dir / f"unsaved_{timestamp}.json"

        # 启动定时器，每 30 秒保存一次
        self._auto_save_loop()
        logger.debug("自动保存已启动，间隔 30 秒")

    def _auto_save_loop(self):
        """自动保存循环"""
        if self.is_recording:
            self._auto_save()
            # 30 秒后再次保存
            self._auto_save_timer_id = self.main_window.root.after(30000, self._auto_save_loop)

    def _auto_save(self):
        """
        自动保存当前转录内容到临时文件。
        """
        if not self._current_tmp_file:
            return

        try:
            import json
            # 保存当前状态
            data = {
                'confirmed_text': self.confirmed_text,
                'current_partial': self.current_partial,
                'title': self.current_document.title if self.current_document else '未命名',
                'session_id': self.current_document.session_id if self.current_document else '',
                'saved_at': datetime.now().isoformat()
            }

            with open(self._current_tmp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"自动保存完成: {self._current_tmp_file.name} ({len(self.confirmed_text)} 字)")

        except Exception as e:
            logger.warning(f"自动保存失败: {e}")

    def _stop_auto_save(self):
        """
        停止自动保存，清理临时文件。
        """
        # 取消定时器
        if self._auto_save_timer_id:
            try:
                self.main_window.root.after_cancel(self._auto_save_timer_id)
            except Exception as e:
                logger.debug(f"取消自动保存定时器失败: {e}")
            self._auto_save_timer_id = None

        # 删除当前临时文件（录音正常完成后不需要保留）
        if self._current_tmp_file and self._current_tmp_file.exists():
            try:
                self._current_tmp_file.unlink()
                logger.debug("自动保存临时文件已清理")
            except Exception as e:
                logger.debug(f"删除临时文件失败: {e}")

        self._current_tmp_file = None

    def run(self):
        """运行应用程序"""
        logger.info("应用程序启动")
        self.main_window.run()
        logger.info("应用程序关闭")
        

if __name__ == "__main__":
    app = VoiceTranscriptionApp()
    app.run()
