"""
语音实时转录系统 - 主应用程序

集成实时转录、格式化、GUI 的完整应用程序。
"""

import sys
import threading
import copy
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue
from uuid import uuid4
from pathlib import Path
from datetime import datetime
from typing import Optional

import customtkinter as ctk
from loguru import logger

# 计算项目根目录
# PyInstaller 打包后，需要从可执行文件位置推算项目根目录
if getattr(sys, 'frozen', False):
    if sys.platform == 'darwin':
        # macOS .app 的数据目录放在 bundle 同级，避免写入只读内部目录。
        try:
            project_root = Path(sys.executable).resolve().parents[2].parent
        except IndexError:
            project_root = Path(sys.executable).parent
    else:
        project_root = Path(sys.executable).parent
else:
    # 源码运行：从当前文件位置推算
    project_root = Path(__file__).parent
    sys.path.insert(0, str(project_root))

from config.settings import settings
from gui.main_window import MainWindow
from gui.export_dialog import ExportDialog
from gui.behavior_config_dialog import BehaviorConfigDialog
from core.realtime_transcriber import RealtimeTranscriber
from core.recording_state import RecordingState
from core.session_store import SessionStore
from core.audio_player import AudioPlayer
from core.review import add_revision
from core.processing import ProcessingContext
from utils.exceptions import ProcessingCancelled
from gui.session_history_dialog import SessionHistoryDialog
from core.formatter.base import FormattedDocument, FormattingStyle, BehaviorMatch
from core.formatter.styles import RawStyle, CleanedStyle, ParagraphStyle, BehaviorMatchStyle
from core.formatter.behavior_matcher import (
    BehaviorConfig, BehaviorDefinition, can_reuse_analysis,
)


def _local_asr_self_check() -> int:
    """本地版构建自检：加载模型后立即释放，不录音。

    用 `VoiceTranscriptionLocal.exe --check-local-asr` 运行；
    退出码 0 表示模型与原生 DLL 均可用，结果同时写入 logs/。
    """
    from types import SimpleNamespace

    from api.local_asr import LocalASRClient
    from config.settings import get_local_asr_model_dir, settings

    config = SimpleNamespace(
        sample_rate=settings.audio.sample_rate,
        language=settings.asr.language,
        vad_silence_ms=settings.asr.vad_silence_ms,
        max_session_duration=1200,
    )
    client = LocalASRClient(config, model_dir=get_local_asr_model_dir())
    started = client.start()
    client.stop()
    if started:
        logger.info('本地 ASR 自检通过')
        return 0
    logger.error(f'本地 ASR 自检失败：{client.last_error}')
    return 1


class VoiceTranscriptionApp:
    """
    语音实时转录应用程序

    集成实时转录、格式化、GUI 的完整应用。
    """
    
    def __init__(self):
        """初始化应用程序"""
        # 配置日志
        logger.remove()
        # PyInstaller console=False 模式下 stderr 可能为 None，需要检查
        if sys.stderr is not None:
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
        self.recording_state = RecordingState.READY
        self._data_lock = threading.RLock()
        self._ui_events = Queue()
        self._display_dirty = threading.Event()
        self._closed = self._closing = False
        self._storage = ThreadPoolExecutor(max_workers=1, thread_name_prefix='session-save')
        self.session_store = SessionStore(project_root / 'sessions')
        self._session_settings = {}
        self._audio_path = None
        self._exported_paths = []
        self._save_future = None
        self._duration_timer_id = None
        self._stop_failed = False
        self._asr_error_notified = False
        self._audio_copy_error = None
        self.transcriber = None
        self.audio_player = AudioPlayer()
        self._revisions = []
        self._draft_dirty = False
        self._format_token = 0
        self._format_context = None
        self._format_worker = None
        self._format_active = False
        self._draft_save_pending = False
        self._export_dialog = None
        self._playback_position = 0.0
        self._playback_error = None
        self.current_document: Optional[FormattedDocument] = None
        self.behavior_config: Optional[BehaviorConfig] = None

        # 实时显示状态：分离已确认文本和当前中间结果
        self.confirmed_text = ""      # 已确认完成的文本
        self.current_partial = ""     # 当前正在识别的中间结果

        # 自动保存临时文件配置
        self._auto_save_timer_id: Optional[str] = None
        
        # 创建主窗口
        self.main_window = MainWindow()
        self._setup_callbacks()
        self.main_window.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.main_window.root.after(50, self._poll_ui_events)
        
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
        self.main_window.workspace.callbacks = {
            'draft': self._on_draft_changed, 'commit': self._commit_review,
            'reprocess': self._reprocess_document,
            'reanalyze': self._reanalyze_document,
            'restore_version': self._restore_version,
            'history': self._open_history, 'rename': self._rename_session,
            'play': self._toggle_playback, 'stop_audio': self._stop_playback,
            'seek': self._seek_audio,
            'cancel_processing': self._cancel_format,
        }
        
    def _on_start_recording(self):
        if self.recording_state.busy or self._closing:
            return
        if self.main_window.get_selected_style() == 'behavior_match' and not self.behavior_config:
            self._open_behavior_config()
        self._capture_review(checkpoint=True)
        self._stop_playback()
        if self.current_document:
            self._set_state(RecordingState.PROCESSING)
            self._save_session(on_saved=self._start_new_recording)
        else:
            self._start_new_recording()

    def _start_new_recording(self):
        if self._closing:
            self._save_session(on_saved=self._finish_close)
            return
        self._stop_auto_save()
        self._recovered_audio_issues = {}
        self._revisions = []
        self._draft_dirty = False
        self._asr_error_notified = False
        language = self.main_window.get_asr_language()
        session_id = 'session_' + uuid4().hex
        self._session_settings = {
            'language': language,
            'vad_silence_ms': self.main_window.get_vad_silence_ms(),
            'device_index': self.main_window.get_selected_device_index(),
            'save_audio': self.main_window.get_save_audio(),
            'style': self.main_window.get_selected_style(),
            'llm_paragraphs': self.main_window.get_enable_llm_paragraphs(),
        }
        self._audio_path = self.session_store.directory / f'{session_id}.wav' if self._session_settings['save_audio'] else None
        self._audio_copy_error = None
        self._exported_paths = []
        self.transcriber = None
        with self._data_lock:
            self.confirmed_text = self.current_partial = ''
            self.current_document = FormattedDocument(
                title=f"录音_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                session_id=session_id, language=language,
            )
        self._show_document()
        self._update_gui_display()
        self.main_window.update_duration(0)
        self._set_state(RecordingState.CONNECTING)
        options = dict(self._session_settings)
        audio_path = self._audio_path

        def start_in_background():
            try:
                transcriber = RealtimeTranscriber(
                    api_key=settings.api.dashscope_api_key or None,
                    language=options['language'], vad_silence_ms=options['vad_silence_ms'],
                    save_audio=options['save_audio'], audio_path=audio_path,
                )
                self.transcriber = transcriber
                started = transcriber.start(
                    on_text=self._update_transcription_data,
                    on_segment=self._on_segment,
                    on_status_change=lambda status: self._post_ui(self._on_transcriber_status, status),
                    device_index=options['device_index'],
                )
                self._post_ui(self._on_start_complete, started, transcriber.last_error)
            except Exception as error:
                self._post_ui(self._on_start_complete, False, str(error))

        threading.Thread(target=start_in_background, name='recording-start', daemon=True).start()

    def _update_duration(self):
        self._duration_timer_id = None
        if self.recording_state.captures_audio and self.transcriber:
            self.main_window.update_duration(int(self.transcriber.get_duration()))
            self.main_window.update_volume(0 if self.recording_state == RecordingState.PAUSED else self.transcriber.get_current_volume())
            recorder = self.transcriber.recorder
            if recorder.write_error or recorder.write_dropped_chunks:
                self.main_window.update_status('音频写入不完整，转录仍在继续；详情已记录到会话')
            elif recorder.dropped_chunks:
                self.main_window.update_status('网络缓冲已满，部分音频未转写；详情已记录到会话')
            self._duration_timer_id = self.main_window.root.after(250, self._update_duration)

    def _on_pause_recording(self):
        if self.recording_state in {RecordingState.RECORDING, RecordingState.RECONNECTING}:
            self.transcriber.pause()
            self._set_state(RecordingState.PAUSED)
            self._save_session()

    def _on_resume_recording(self):
        if self.recording_state == RecordingState.PAUSED:
            self.transcriber.resume()
            self._set_state(RecordingState.RECORDING)

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
        # ASR 线程只更新受锁保护的数据，不调用任何 Tk 方法。
        with self._data_lock:
            if is_final:
                self.confirmed_text += text + ' '
                if self.current_document:
                    self.current_document.raw_text = self.confirmed_text.strip()
                self.current_partial = ''
            else:
                self.current_partial = text
        self._display_dirty.set()

    def _update_gui_display(self):
        with self._data_lock:
            confirmed, partial = self.confirmed_text, self.current_partial
            segments = list(self.current_document.segments) if self.current_document else []
        self.main_window.render_live(confirmed, partial, segments)

    def _on_segment(self, segment):
        with self._data_lock:
            if self.current_document:
                self.current_document.segments.append(segment)
        self._display_dirty.set()

    def _append_transcription(self, text: str, is_final: bool = True):
        """
        兼容旧接口：更新转录文本
        保留这个方法是为了兼容，新代码使用 _update_transcription_data + _update_gui_display
        """
        self._update_transcription_data(text, is_final)
        self._update_gui_display()
        
    def _on_stop_recording(self):
        if not self.recording_state.captures_audio:
            return
        self._set_state(RecordingState.STOPPING)
        self._stop_failed = False
        self._stop_auto_save()
        self._save_session()
        transcriber = self.transcriber
        output_path = Path(settings.document.output_dir) / f'{self.current_document.title}.wav'

        def stop_in_background():
            try:
                text = transcriber.stop()
                if self._audio_path:
                    try:
                        transcriber.save_audio_wav(output_path)
                    except Exception as error:
                        self._audio_copy_error = str(error)
                        logger.error(f'原始录音复制到输出目录失败，会话录音仍保留: {error}')
                self._post_ui(self._on_stop_complete, text)
            except Exception as error:
                self._post_ui(self._on_stop_error, str(error))

        threading.Thread(target=stop_in_background, name='recording-stop', daemon=True).start()

    def _format_document(self, force: bool = False):
        if not self.current_document:
            return
        if self._closing:
            self._save_session(on_saved=self._finish_close)
            return
        if self._format_worker and self._format_worker.is_alive():
            self._set_state(RecordingState.SAVED)
            if not self.current_document.formatted_text and not self.current_document.draft_edited:
                self.current_document.formatted_text = self.current_document.raw_text
            self._show_document()
            self._save_session()
            self.main_window.update_status('上次 AI 请求仍在结束；原文已保存，请稍后点击重新整理。')
            return
        style = self.main_window.get_selected_style()
        self._session_settings.update(style=style, llm_paragraphs=self.main_window.get_enable_llm_paragraphs())
        if style == 'cleaned':
            formatter = CleanedStyle()
        elif style == 'paragraphs':
            formatter = ParagraphStyle(enable_llm_reorganization=self.main_window.get_enable_llm_paragraphs())
        elif style == 'behavior_match':
            formatter = BehaviorMatchStyle(copy.deepcopy(self.behavior_config))
        else:
            formatter = RawStyle()

        # 原文、配置、模型和提示词版本均未变化时复用上次分析，
        # 使重复整理结果稳定，并避免重复消耗 Token。
        if (style == 'behavior_match' and not force
                and can_reuse_analysis(self.current_document, self.behavior_config, settings.api.bailian_model)):
            self._set_state(RecordingState.PROCESSING)
            self._format_token += 1
            token = self._format_token
            self._format_active = True
            document = copy.deepcopy(self.current_document)
            try:
                result = formatter.render_reused(document)
            except Exception as error:
                logger.warning(f'复用上次分析失败，改为重新分析: {error}')
                self._format_active = False
            else:
                self.main_window.update_status('已复用上次分析结果；如需重新判定，请点击“重新分析”')
                self._on_format_complete(result, None, token)
                return

        self._set_state(RecordingState.PROCESSING)
        self._format_token += 1
        token = self._format_token
        context = self._format_context = ProcessingContext(
            lambda message: self._post_ui(self._on_format_progress, token, message))
        self._format_active = True
        self._on_format_progress(token, '正在准备整理…')
        if force:
            self.main_window.update_status('正在重新分析；LLM 判定可能因随机性有所不同')
        document = copy.deepcopy(self.current_document)
        document.behavior_matches = []
        document.behaviors_config = None
        document.analysis_text = ''
        document.analysis_fingerprint = ''
        document.analysis_model = ''
        document.analysis_at = ''
        document.draft_edited = False
        document.processing_warnings = []
        def format_in_background():
            try:
                context.report('正在整理文稿')
                result = formatter.format(document, context=context)
                context.check()
                self._post_ui(self._on_format_complete, result, None, token)
            except ProcessingCancelled:
                pass
            except Exception as error:
                self._post_ui(self._on_format_error, error, None, token)
        self._format_worker = threading.Thread(target=format_in_background, name='document-format', daemon=True)
        self._format_worker.start()

    def _on_format_progress(self, token, message):
        if token == self._format_token and self._format_active and not self._closing:
            self.main_window.workspace.show_processing(message, cancellable=True)

    def _cancel_format(self):
        if not self._format_active or self._closing:
            return
        self._format_context.cancel()
        self._format_token += 1
        self._format_active = False
        if not self.current_document.formatted_text and not self.current_document.draft_edited:
            self.current_document.formatted_text = self.current_document.raw_text
            self.current_document.word_count = len(self.current_document.raw_text)
        self._set_state(RecordingState.SAVED)
        self._show_document()
        self._save_session()
        self.main_window.update_status('已取消整理，原文和原稿保留；已发送的 AI 请求可能仍在结束。')

    def _on_format_complete(self, formatted_doc, processing_window=None, token=None):
        if token is not None and token != self._format_token:
            return
        if not self.current_document or formatted_doc.session_id != self.current_document.session_id:
            return
        self._format_active = False
        self.main_window.workspace.show_processing('正在保存整理结果…', cancellable=False)
        self.current_document = formatted_doc
        self._revisions = add_revision(self._revisions, formatted_doc.formatted_text, '自动整理')
        self._draft_dirty = False
        self._update_formatted_display()
        self._save_session(on_saved=self._on_processing_saved, persisted_state=RecordingState.SAVED)

    def _on_format_error(self, error: Exception, processing_window=None, token=None):
        if token is not None and token != self._format_token:
            return
        self._format_active = False
        """格式化错误回调（在主线程执行）"""
        # 关闭处理中弹窗
        if processing_window:
            processing_window.destroy()
        self._set_state(RecordingState.SAVED)
        self._show_document()
        if self._closing:
            self._save_session(on_saved=self._finish_close)
            return
        # 显示错误
        import tkinter.messagebox as messagebox
        message = getattr(error, 'message', str(error))
        if message == "API Key未设置" and settings.asr.provider == "local":
            message = (
                "未配置百炼 API Key，AI 整理不可用；本地转写和原始文稿不受影响。\n"
                "请在设置中填写 BAILIAN_API_KEY 后重试。"
            )
        messagebox.showerror(
            "格式化失败",
            f"文档格式化过程中发生错误:\n\n{message}\n\n请检查网络连接和 API Key 配置后重试。"
        )
        logger.error(f"格式化文档失败: {error}")

    def _update_formatted_display(self):
        self._show_document()

    def _prompt_export(self):
        self.main_window.update_status('会话已保存，可以审阅、修订或导出')

    def _on_export_document(self):
        """导出文档回调"""
        if self.recording_state.busy or self._closing:
            return
        if not self.current_document:
            import tkinter.messagebox as messagebox
            messagebox.showwarning(
                "无法导出",
                "没有可导出的文档，请先进行录音。"
            )
            return
            
        self._capture_review(checkpoint=True)
        self._save_session()
        # 打开导出对话框
        self._export_dialog = ExportDialog(
            self.main_window.root,
            copy.deepcopy(self.current_document),
            on_export=lambda path, identity=self.current_document.session_id: self._on_export_complete(path, identity)
        )
        
    def _on_export_complete(self, file_path: Path, session_id=None):
        """
        导出完成回调

        Args:
            file_path: 导出的文件路径
        """
        if session_id and (not self.current_document or self.current_document.session_id != session_id):
            def save_export():
                try:
                    snapshot = self.session_store.load(session_id)
                    snapshot.setdefault('exported_paths', []).append(str(file_path))
                    self.session_store.save(snapshot)
                except Exception as error:
                    logger.error(f'保存历史会话导出记录失败: {error}')
            self._storage.submit(save_export)
            return
        self._exported_paths.append(str(file_path))
        self._save_session()
        logger.info(f"文档已导出: {file_path}")
        self.main_window.update_status(f"文档已导出: {file_path.name}")

    def _open_behavior_config(self):
        """打开行为配置对话框"""
        if not self.recording_state.busy:
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
        启动时检查API配置，如果未配置弹出配置对话框让用户直接输入。
        """
        from config.settings import check_api_configuration, settings
        status = check_api_configuration()

        # 本地版不需要 DashScope Key；云端版语义不变。
        if not status["asr_configured"]:
            def show_config_dialog():
                from gui.api_settings_dialog import APISettingsDialog
                # 获取当前已有的值（可能为空）
                current_dashscope = settings.api.dashscope_api_key
                current_bailian = settings.api.bailian_api_key
                # 打开对话框，首次启动，保存后退出让用户重启
                dialog = APISettingsDialog(
                    self.main_window.root,
                    initial_dashscope=current_dashscope,
                    initial_bailian=current_bailian,
                    initial_region=settings.api.dashscope_region,
                    initial_workspace=settings.api.dashscope_workspace_id,
                    initial_proxy_mode=settings.api.proxy_mode,
                    initial_proxy_url=settings.api.proxy_url,
                    is_first_launch=True,
                    dashscope_optional=(status.get("asr_provider") == "local"),
                )

            # 在主窗口加载后显示对话框
            self.main_window.root.after(500, show_config_dialog)
            logger.warning("ASR 未配置，弹出配置对话框")

    def _check_unsaved_recording(self):
        # 在磁盘线程加载快照；兼容旧版 .tmp 恢复文件。
        def load():
            data = self.session_store.latest()
            if data is None:
                import json
                for path in sorted(self.tmp_dir.glob('unsaved_*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
                    try:
                        data = json.loads(path.read_text(encoding='utf-8'))
                        break
                    except (OSError, ValueError):
                        continue
            self._post_ui(self._offer_recovery, data)
        self._storage.submit(load)

    def _offer_recovery(self, data):
        if not data or self.recording_state != RecordingState.READY or self._closing:
            return
        import tkinter.messagebox as messagebox
        title = data.get('document', data).get('title', '未命名录音')
        if messagebox.askyesno('恢复上次会话', f'发现已保存的会话：{title}。是否打开？'):
            self._restore_unsaved_recording(data)

    def _restore_unsaved_recording(self, data: dict):
        self.audio_player.stop(reset=True)
        self._playback_position = 0
        self.transcriber = None
        self._revisions = [item for item in data.get('revisions', []) if isinstance(item, dict)
                           and all(isinstance(item.get(key), str) for key in ('id', 'text', 'label', 'created_at'))][-20:]
        self._draft_dirty = False
        if 'document' in data:
            self.current_document = self.session_store.restore_document(data)
            self._session_settings = data.get('settings', {})
            self._audio_path = Path(data['audio_path']) if data.get('audio_path') else None
            self._exported_paths = data.get('exported_paths', [])
            self._recovered_audio_issues = data.get('audio_issues', {})
            self.behavior_config = None
            if data.get('behavior_config'):
                self.behavior_config = BehaviorConfig.from_dict(data['behavior_config'])
        else:
            self.current_document = FormattedDocument(
                title=data.get('title', '恢复的录音'),
                session_id=data.get('session_id', 'session_' + uuid4().hex),
                raw_text=(data.get('confirmed_text', '') + data.get('current_partial', '')).strip(),
            )
        # 恢复后的原文已包含未确认句尾，不再重复附加中间结果。
        self.confirmed_text = self.current_document.raw_text
        self.current_partial = ''
        if not self.current_document.formatted_text and not self._revisions and not self.current_document.draft_edited:
            self.current_document.formatted_text = self.current_document.raw_text
            self.current_document.word_count = len(self.current_document.formatted_text)
        self._audio_copy_error = data.get('audio_copy_error')
        self.main_window.set_review_style(self.current_document.style.value, self._session_settings.get('llm_paragraphs', False))
        self._set_state(RecordingState.SAVED)
        self._update_gui_display()
        self._update_formatted_display()
        self.main_window.update_duration(int(self.current_document.duration_seconds))
        self._save_session()

    def _start_auto_save(self):
        self._stop_auto_save()
        self._auto_save_loop()

    def _auto_save_loop(self):
        self._auto_save_timer_id = None
        if self.recording_state.captures_audio:
            self._auto_save()
            self._auto_save_timer_id = self.main_window.root.after(5000, self._auto_save_loop)

    def _auto_save(self):
        # 慢磁盘时跳过周期快照，防止积压；结束与退出快照始终提交。
        if self._save_future is None or self._save_future.done():
            self._save_session()

    def _stop_auto_save(self):
        if self._auto_save_timer_id:
            self.main_window.root.after_cancel(self._auto_save_timer_id)
            self._auto_save_timer_id = None

    def _post_ui(self, callback, *args):
        if not self._closed:
            self._ui_events.put((callback, args))

    def _poll_ui_events(self):
        if self._closed:
            return
        for _ in range(100):
            try:
                callback, args = self._ui_events.get_nowait()
            except Empty:
                break
            try:
                callback(*args)
            except Exception:
                logger.exception('处理界面事件失败')
            if self._closed:
                return
        if self._display_dirty.is_set():
            self._display_dirty.clear()
            self._update_gui_display()
        self._flush_draft_save()
        self._poll_playback()
        self.main_window.root.after(50, self._poll_ui_events)

    def _set_state(self, state):
        if state == RecordingState.STOPPING and self._duration_timer_id:
            self.main_window.root.after_cancel(self._duration_timer_id)
            self._duration_timer_id = None
        self.recording_state = state
        self.is_recording = state in {RecordingState.RECORDING, RecordingState.RECONNECTING}
        self.main_window.set_recording_state(state)
        if state != RecordingState.PROCESSING:
            self.main_window.workspace.show_processing(None)

    def _on_transcriber_status(self, status):
        if not self.recording_state.captures_audio or self.recording_state == RecordingState.PAUSED:
            return
        if status.startswith('asr_error:'):
            message = status.split(':', 1)[1].strip()
            self._set_state(RecordingState.RECONNECTING)
            self.main_window.update_status(f'语音识别异常：{message}')
            if not self._asr_error_notified:
                self._asr_error_notified = True
                import tkinter.messagebox as messagebox
                messagebox.showwarning('语音识别异常', message)
            return
        if status == 'reconnecting':
            self._set_state(RecordingState.RECONNECTING)
        elif status == 'recording':
            self._set_state(RecordingState.RECORDING)

    def _on_start_complete(self, started, error):
        if not started:
            self._set_state(RecordingState.ERROR)
            self._save_session(on_saved=self._finish_close if self._closing else None)
            if not self._closing:
                import tkinter.messagebox as messagebox
                messagebox.showerror('启动失败', error or '无法启动录音，请检查麦克风与网络配置。')
            return
        self._set_state(RecordingState.RECORDING)
        self._update_duration()
        self._start_auto_save()
        if self._closing:
            self._on_stop_recording()

    def _on_stop_complete(self, full_text):
        self._stop_failed = False
        with self._data_lock:
            self.current_document.raw_text = (self.confirmed_text + self.current_partial).strip() or full_text.strip()
            self.current_document.word_count = len(self.current_document.raw_text)
            self.current_document.duration_seconds = self.transcriber.get_audio_duration()
        self.main_window.update_duration(int(self.current_document.duration_seconds))
        self.main_window.update_volume(0)
        self._update_gui_display()
        # 必须确认原文已经落盘，才允许进入后处理或退出。
        self._save_session(on_saved=self._on_raw_saved, persisted_state=RecordingState.SAVED)

    def _on_stop_error(self, error):
        # 发送线程未退出时保持停止状态，禁止启动新会话；允许再次尝试停止。
        self.main_window.update_status('停止未完成，正在保留会话，请重试')
        self._save_session()
        self._closing = False
        self._stop_failed = True
        self.main_window.stop_btn.configure(state='normal', command=self._retry_stop)
        import tkinter.messagebox as messagebox
        messagebox.showerror('停止未完成', error)

    def _retry_stop(self):
        self.main_window.stop_btn.configure(command=self.main_window._on_stop_click)
        self._set_state(RecordingState.PAUSED)
        self._on_stop_recording()

    def _on_raw_saved(self):
        if self._closing:
            self._finish_close()
            return
        recorder = self.transcriber.recorder
        if (recorder.dropped_chunks or recorder.write_dropped_chunks or recorder.write_error
                or self.transcriber.failed_audio_bytes or self.transcriber.unsent_audio_bytes
                or self._audio_copy_error):
            import tkinter.messagebox as messagebox
            messagebox.showwarning(
                '录音存在异常',
                '会话已保存。部分音频未完成转写、保存或输出复制，详情已记录。\n'
                + ('请核查会话目录中的原始 WAV 录音。' if self._audio_path else '本次未启用原始音频保存。'),
            )
        self._set_state(RecordingState.PROCESSING)
        try:
            self._format_document()
        except Exception as error:
            self._on_format_error(error, None)

    def _on_processing_saved(self):
        self._set_state(RecordingState.SAVED)
        self._show_document()
        if self._closing:
            self._finish_close()
        else:
            if self.current_document.processing_warnings:
                self.main_window.update_status('会话已保存，部分 AI 整理未完成，请查看工作区的整理说明。')
            else:
                self._prompt_export()

    def _session_snapshot(self):
        with self._data_lock:
            document = self.current_document.to_dict()
            if self.recording_state.captures_audio or self.recording_state == RecordingState.STOPPING:
                document['raw_text'] = (self.confirmed_text + self.current_partial).strip()
                document['word_count'] = len(document['raw_text'])
                if self.transcriber:
                    document['duration_seconds'] = self.transcriber.get_audio_duration()
            issues = getattr(self, '_recovered_audio_issues', {})
            if self.transcriber:
                recorder = self.transcriber.recorder
                issues = {
                    'network_dropped_chunks': recorder.dropped_chunks,
                    'audio_dropped_chunks': recorder.write_dropped_chunks,
                    'write_error': recorder.write_error,
                    'failed_audio_bytes': self.transcriber.failed_audio_bytes,
                    'unsent_audio_bytes': self.transcriber.unsent_audio_bytes,
                    'gaps': copy.deepcopy(recorder.gaps),
                    'sample_rate': recorder.config.sample_rate,
                    'channels': recorder.config.channels,
                }
            return {
                'version': 1, 'saved_at': datetime.now().isoformat(),
                'state': self.recording_state.value, 'document': document,
                'confirmed_text': self.confirmed_text, 'current_partial': self.current_partial,
                'settings': dict(self._session_settings),
                'behavior_config': self.behavior_config.to_dict() if self.behavior_config else None,
                'audio_path': str(self._audio_path) if self._audio_path else None,
                'audio_issues': issues, 'exported_paths': list(self._exported_paths),
                'audio_copy_error': self._audio_copy_error,
                'revisions': copy.deepcopy(self._revisions),
            }

    def _save_session(self, on_saved=None, persisted_state=None):
        if not self.current_document:
            if on_saved:
                on_saved()
            return
        snapshot = self._session_snapshot()
        self._draft_save_pending = False
        if persisted_state:
            snapshot['state'] = persisted_state.value
        session_id = self.current_document.session_id
        def save():
            try:
                self.session_store.save(snapshot)
            except Exception as error:
                self._post_ui(self._on_save_error, session_id, str(error), on_saved is not None)
            else:
                if on_saved:
                    self._post_ui(on_saved)
        self._save_future = self._storage.submit(save)

    def _on_save_error(self, session_id, error, required):
        if not self.current_document or self.current_document.session_id != session_id:
            return
        self.main_window.update_status('会话保存失败，请检查磁盘空间与权限')
        logger.error(error)
        if required:
            self._closing = False
            self._set_state(RecordingState.ERROR)
            import tkinter.messagebox as messagebox
            messagebox.showerror('会话保存失败', f'{error}\n原文仍在当前窗口，可以导出后再退出。')

    def _on_close(self):
        if self._closing:
            return
        if self._export_dialog and getattr(self._export_dialog, 'is_exporting', False) is True:
            self.main_window.update_status('文档正在导出，请完成后再退出。')
            self._export_dialog.window.lift()
            return
        self._capture_review(checkpoint=True)
        self._closing = True
        if self._format_context:
            self._format_context.cancel()
            self._format_token += 1
            self._format_active = False
        self._stop_playback()
        self._stop_auto_save()
        if self.recording_state.captures_audio:
            self._on_stop_recording()
        elif self.recording_state in {RecordingState.CONNECTING, RecordingState.STOPPING}:
            if self._stop_failed:
                self._retry_stop()
            else:
                self.main_window.update_status('正在结束录音并保存后退出…')
        elif self.recording_state == RecordingState.PROCESSING:
            # 原文已经持久保存，退出不必等待远程整理完成。
            self._save_session(on_saved=self._finish_close)
        else:
            self._save_session(on_saved=self._finish_close)

    def _finish_close(self):
        if self._closed:
            return
        self._closed = True
        self.audio_player.close()
        self._stop_auto_save()
        if self._duration_timer_id:
            self.main_window.root.after_cancel(self._duration_timer_id)
        self._storage.shutdown(wait=False)
        self.main_window.close()

    def _show_document(self):
        if self.current_document:
            hint = None
            issues = self._session_snapshot()['audio_issues']
            if issues.get('audio_dropped_chunks') or issues.get('write_error'):
                hint = '录音有保存缺口，片段定位可能偏移，请结合原文核查'
            self.main_window.show_document(self.current_document, self._revisions, bool(self._audio_path), hint)

    def _on_draft_changed(self, text):
        if self.recording_state.busy or not self.current_document or not isinstance(text, str):
            return
        if text == self.current_document.formatted_text:
            return
        if not self._revisions:
            self._revisions = add_revision([], self.current_document.formatted_text or self.current_document.raw_text, '初始整理稿')
        self.current_document.formatted_text = text
        self.current_document.draft_edited = True
        self.current_document.word_count = len(text)
        self._draft_dirty = True
        self._draft_save_pending = True
        self._flush_draft_save()
        if self.current_document.behavior_matches:
            warning = '行为分析基于原始整理文本；修改原文后建议重新整理以更新标记与频次。'
            if warning not in self.current_document.processing_warnings:
                self.current_document.processing_warnings.append(warning)
            self.main_window.update_status('修订稿已保存；行为分析仍基于原始整理文本，如需更新请重新整理')
        else:
            self.main_window.update_status('修订稿正在自动保存；原始转录保留')

    def _flush_draft_save(self):
        if (self._draft_save_pending and not self._closing and not self.recording_state.busy
                and (self._save_future is None or self._save_future.done())):
            self._save_session()

    def _capture_review(self, checkpoint=False):
        if not self.current_document or self.recording_state.busy:
            return
        text = self.main_window.workspace.get_draft()
        if not isinstance(text, str):
            return
        self.main_window.workspace.cancel_edit_timer()
        self._on_draft_changed(text)
        if checkpoint and (self._draft_dirty or not self._revisions
                           or self._revisions[-1]['text'] != self.current_document.formatted_text):
            self._revisions = add_revision(self._revisions, self.current_document.formatted_text,
                                           '人工修订' if self._draft_dirty else '整理稿快照')
            self._draft_dirty = False

    def _commit_review(self):
        if self.recording_state.busy or not self.current_document:
            return
        self._capture_review(checkpoint=True)
        self.main_window.workspace.refresh_revisions(self._revisions)
        session_id = self.current_document.session_id
        def saved():
            if self.current_document.session_id == session_id:
                self.main_window.update_status('修订已保存，原始转录保留')
        self._save_session(on_saved=saved)

    def _restore_version(self, identity):
        if self.recording_state.busy or not self.current_document:
            return
        revision = next((item for item in self._revisions if item['id'] == identity), None)
        if not revision:
            return
        text = revision['text']
        self._capture_review(checkpoint=True)
        self.current_document.formatted_text = text
        self.current_document.draft_edited = True
        self.current_document.word_count = len(text)
        self._revisions = add_revision(self._revisions, text, '恢复版本')
        self._draft_dirty = False
        self._save_session()
        self._show_document()

    def _rename_session(self, title):
        if self.recording_state.busy or not self.current_document:
            return
        title = title.strip()
        if not title or len(title) > 120:
            self.main_window.update_status('标题请输入 1–120 个字符')
            return
        self.current_document.title = title
        self._capture_review(checkpoint=True)
        self._save_session()
        self.main_window.update_status('标题已提交保存')

    def _reprocess_document(self, force: bool = False):
        if self.recording_state.busy or not self.current_document:
            return
        if self._format_worker and self._format_worker.is_alive():
            self.main_window.update_status('上次 AI 请求仍在结束，请稍后重试整理。')
            return
        self._capture_review(checkpoint=True)
        self._stop_playback()
        self._set_state(RecordingState.PROCESSING)
        self._save_session(on_saved=lambda: self._format_document(force=force))

    def _reanalyze_document(self):
        """强制重新调用模型，忽略可复用的上次分析。"""
        self._reprocess_document(force=True)

    def _open_history(self):
        if self.recording_state.busy or self._closing:
            return
        previous_state = self.recording_state
        self._capture_review(checkpoint=True)
        self._set_state(RecordingState.PROCESSING)
        self.main_window.update_status('正在读取会话历史…')
        def load():
            try:
                rows = self.session_store.list_sessions()
                self._post_ui(self._show_history, rows, previous_state)
            except Exception as error:
                self._post_ui(self._on_history_error, str(error))
        if self.current_document:
            self._save_session(on_saved=lambda: self._storage.submit(load))
        else:
            self._storage.submit(load)

    def _show_history(self, rows, previous_state):
        if self._closing:
            self._save_session(on_saved=self._finish_close)
            return
        self._set_state(previous_state)
        self._show_document()
        SessionHistoryDialog(self.main_window.root, rows, self._open_session)

    def _open_session(self, session_id):
        if self.recording_state.busy or self._closing:
            return
        self._capture_review(checkpoint=True)
        self._stop_playback()
        self._set_state(RecordingState.PROCESSING)
        def load():
            try:
                data = self.session_store.load(session_id)
                self._post_ui(self._on_session_loaded, data)
            except Exception as error:
                self._post_ui(self._on_history_error, str(error))
        if self.current_document:
            self._save_session(on_saved=lambda: self._storage.submit(load))
        else:
            self._storage.submit(load)

    def _on_session_loaded(self, data):
        if self._closing:
            self._save_session(on_saved=self._finish_close)
            return
        self._restore_unsaved_recording(data)

    def _on_history_error(self, error):
        self._set_state(RecordingState.ERROR)
        self._show_document()
        self.main_window.update_status(f'无法打开会话：{error}')
        if self._closing:
            self._save_session(on_saved=self._finish_close)

    def _toggle_playback(self):
        if self.recording_state.busy or not self.current_document or not self._audio_path:
            return
        if self.audio_player.state()['playing']:
            self.audio_player.stop()
        else:
            duration = self.current_document.duration_seconds
            if duration and self._playback_position >= duration:
                self._playback_position = 0
            self.audio_player.play(self._audio_path, self._playback_position)

    def _stop_playback(self):
        self.audio_player.stop(reset=True)
        self._playback_position = 0
        self._playback_error = None

    def _seek_audio(self, seconds, play=False):
        if self.recording_state.busy or not self.current_document:
            return
        if not self._audio_path:
            self.main_window.update_status('此会话未保存原始音频，可查看片段文字')
            return
        resume = play or self.audio_player.state()['playing']
        self.audio_player.stop(reset=True)
        self._playback_position = min(max(0, seconds), self.current_document.duration_seconds)
        if resume:
            self.audio_player.play(self._audio_path, self._playback_position)

    def _poll_playback(self):
        if not self.current_document or self.recording_state.busy:
            return
        state = self.audio_player.state()
        if state['playing']:
            self._playback_position = state['position']
        elif state['position'] > self._playback_position and state['duration']:
            self._playback_position = state['position']
        self.main_window.workspace.update_playback(state['playing'], self._playback_position, self.current_document.duration_seconds)
        if state['error'] and state['error'] != self._playback_error:
            self._playback_error = state['error']
            self.main_window.update_status(f"无法回听录音：{state['error']}")

    def run(self):
        """运行应用程序"""
        logger.info("应用程序启动")
        self.main_window.run()
        logger.info("应用程序关闭")
        

if __name__ == "__main__":
    if '--check-local-asr' in sys.argv:
        raise SystemExit(_local_asr_self_check())
    app = VoiceTranscriptionApp()
    app.run()
