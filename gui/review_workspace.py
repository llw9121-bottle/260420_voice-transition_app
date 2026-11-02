"""文稿工作区：原文、可编辑整理稿、对照、片段及分析依据。"""

import tkinter as tk
import customtkinter as ctk

from core.review import changed_ranges, clock_text, segment_ranges
from gui.theme import AppColors, AppFonts


class ReviewWorkspace(ctk.CTkFrame):
    def __init__(self, parent, font_size=16):
        super().__init__(parent, fg_color='transparent')
        self.callbacks = {}
        self.document = None
        self._revisions = []
        self._busy = False
        self._loading = False
        self._edit_timer = None
        self._search_timer = None
        self._confirmed = ''
        self._raw_session = None
        self._segment_page = 0
        self._match_page = 0
        self._last_compact = None
        self._sidebar_visible = True
        self._font_size = font_size
        self._segments = []
        self._audio_available = False
        self._dragging_audio = False
        self._search_matches = []
        self._search_index = -1
        self.scroll_lock_var = ctk.BooleanVar(value=False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color='transparent')
        header.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)
        self.title_entry = ctk.CTkEntry(header, placeholder_text='会话标题', height=38, font=AppFonts.TITLE)
        self.title_entry.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        self.rename_btn = self._button(header, '保存标题', self._rename, width=76)
        self.rename_btn.grid(row=0, column=1, padx=(0, 8))
        self.details_btn = self._button(header, '收起侧栏', self.toggle_sidebar, width=84)
        self.details_btn.grid(row=0, column=2)

        main = ctk.CTkFrame(self, fg_color=AppColors.SURFACE_RAISED, corner_radius=12)
        main.grid(row=1, column=0, sticky='nsew')
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)

        toolbar = ctk.CTkFrame(main, fg_color='transparent')
        toolbar.grid(row=0, column=0, sticky='ew', padx=16, pady=(12, 0))
        toolbar.grid_columnconfigure(0, weight=1)
        self.search_entry = ctk.CTkEntry(toolbar, placeholder_text='搜索当前文稿 · Ctrl+F', height=32)
        self.search_entry.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        self.search_entry.bind('<KeyRelease>', self._schedule_search)
        self.search_entry.bind('<Return>', lambda event: self.search_next())
        self.search_count = ctk.CTkLabel(toolbar, text='', width=52, font=AppFonts.BODY_SMALL)
        self.search_count.grid(row=0, column=1)
        self._button(toolbar, '上一个', lambda: self.search_next(-1), width=60).grid(row=0, column=2, padx=4)
        self._button(toolbar, '下一个', self.search_next, width=60).grid(row=0, column=3)

        actions = ctk.CTkFrame(main, fg_color='transparent')
        actions.grid(row=1, column=0, sticky='ew', padx=16, pady=(10, 0))
        self.commit_btn = self._button(actions, '保存修订', lambda: self._call('commit'), width=82, primary=True)
        self.commit_btn.pack(side='left', padx=(0, 8))
        self.undo_btn = self._button(actions, '撤销', lambda: self._undo(False), width=54)
        self.undo_btn.pack(side='left', padx=(0, 4))
        self.redo_btn = self._button(actions, '重做', lambda: self._undo(True), width=54)
        self.redo_btn.pack(side='left')
        self.reprocess_btn = self._button(actions, '重新整理', lambda: self._call('reprocess'), width=82)
        self.reprocess_btn.pack(side='right')
        self.reanalyze_btn = self._button(actions, '重新分析', lambda: self._call('reanalyze'), width=82)
        self.reanalyze_btn.pack(side='right', padx=(0, 8))

        self.processing_frame = ctk.CTkFrame(main, fg_color=AppColors.SURFACE, corner_radius=8)
        self.processing_frame.grid(row=2, column=0, sticky='ew', padx=16, pady=(10, 0))
        self.processing_frame.grid_columnconfigure(0, weight=1)
        self.processing_label = ctk.CTkLabel(self.processing_frame, text='', anchor='w', font=AppFonts.BODY_SMALL)
        self.processing_label.grid(row=0, column=0, sticky='ew', padx=12, pady=8)
        self.cancel_processing_btn = self._button(self.processing_frame, '取消整理', lambda: self._call('cancel_processing'), width=80)
        self.cancel_processing_btn.grid(row=0, column=1, padx=8)
        self.processing_bar = ctk.CTkProgressBar(self.processing_frame, mode='indeterminate', height=3)
        self.processing_bar.grid(row=1, column=0, columnspan=2, sticky='ew', padx=12, pady=(0, 8))
        self.processing_frame.grid_remove()

        self.tabs = ctk.CTkTabview(main, command=self._on_tab, fg_color='transparent', corner_radius=8)
        self.tabs.grid(row=3, column=0, sticky='nsew', padx=12, pady=(2, 0))
        for name in ('原始转录', '整理稿', '对照'):
            tab = self.tabs.add(name)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)
        self.raw_text = self._text(self.tabs.tab('原始转录'))
        self.raw_text.grid(row=0, column=0, sticky='nsew')
        self.raw_text._textbox.mark_set('confirmed_end', '1.0')
        self.raw_text._textbox.mark_gravity('confirmed_end', 'left')
        self.raw_text.tag_config('partial', foreground=AppColors.TEXT_SECONDARY[0])
        self.raw_text.bind('<MouseWheel>', lambda event: self.after(30, self._check_scroll))
        self.raw_text._y_scrollbar.bind('<ButtonRelease-1>', lambda event: self.after(30, self._check_scroll), add='+')
        self.draft_text = self._text(self.tabs.tab('整理稿'), editable=True)
        self.draft_text.grid(row=0, column=0, sticky='nsew')
        self.draft_text._textbox.configure(undo=True, autoseparators=True, maxundo=100)
        self.draft_text.bind('<<Modified>>', self._on_edit)
        compare = self.tabs.tab('对照')
        compare.grid_columnconfigure(1, weight=1)
        compare.grid_rowconfigure(1, weight=1)
        compare.grid_rowconfigure(0, weight=0)
        ctk.CTkLabel(compare, text='转录原文 · 只读', anchor='w', font=AppFonts.BODY_SMALL).grid(row=0, column=0, sticky='w')
        ctk.CTkLabel(compare, text='当前整理稿 · 高亮变化', anchor='w', font=AppFonts.BODY_SMALL).grid(row=0, column=1, sticky='w')
        self.compare_raw = self._text(compare)
        self.compare_raw.grid(row=1, column=0, sticky='nsew', padx=(0, 5))
        self.compare_draft = self._text(compare)
        self.compare_draft.grid(row=1, column=1, sticky='nsew', padx=(5, 0))
        for widget in (self.compare_raw, self.compare_draft):
            widget.tag_config('changed', background='#FEF3C7', foreground='#78350F')

        footer = ctk.CTkFrame(main, fg_color='transparent')
        footer.grid(row=5, column=0, sticky='ew', padx=16, pady=6)
        self.warning_label = ctk.CTkLabel(main, text='', anchor='w', justify='left', wraplength=640,
                                          font=AppFonts.BODY_SMALL, text_color=AppColors.WARNING)
        self.warning_label.grid(row=4, column=0, sticky='ew', padx=20, pady=4)
        self.warning_label.grid_remove()
        self.document_info = ctk.CTkLabel(footer, text='开始录音，或从会话历史打开记录', font=AppFonts.BODY_SMALL, text_color=AppColors.TEXT_SECONDARY)
        self.document_info.pack(side='left')
        self.latest_btn = self._button(footer, '回到最新 ↓', self.follow_latest, width=94)
        self.latest_btn.pack(side='right')

        playback = ctk.CTkFrame(main, fg_color=AppColors.SURFACE, corner_radius=8)
        playback.grid(row=6, column=0, sticky='ew', padx=16, pady=(0, 16))
        playback.grid_columnconfigure(2, weight=1)
        self.play_btn = self._button(playback, '播放', lambda: self._call('play'), width=56)
        self.play_btn.grid(row=0, column=0, padx=(8, 4), pady=10)
        self.stop_audio_btn = self._button(playback, '停止', lambda: self._call('stop_audio'), width=56)
        self.stop_audio_btn.grid(row=0, column=1, padx=(0, 8))
        self.audio_slider = ctk.CTkSlider(playback, from_=0, to=1, command=self._preview_seek)
        self.audio_slider.set(0)
        self.audio_slider.grid(row=0, column=2, sticky='ew', padx=4)
        self.audio_slider.bind('<ButtonPress-1>', self._begin_seek)
        self.audio_slider.bind('<ButtonRelease-1>', self._finish_seek)
        self.audio_time = ctk.CTkLabel(playback, text='00:00 / 00:00', width=110, font=AppFonts.MONO_NUMBERS)
        self.audio_time.grid(row=0, column=3, padx=8)
        self.audio_hint = ctk.CTkLabel(playback, text='保存原始音频后可回听', font=AppFonts.BODY_SMALL, text_color=AppColors.TEXT_SECONDARY)
        self.audio_hint.grid(row=1, column=0, columnspan=4, sticky='w', padx=12, pady=(0, 8))

        self.sidebar = ctk.CTkFrame(self, width=290, fg_color=AppColors.SURFACE_RAISED, corner_radius=12)
        self.sidebar.grid(row=1, column=1, sticky='nsew', padx=(12, 0))
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self.sidebar, text='核查与版本', font=AppFonts.TITLE, anchor='w').grid(row=0, column=0, sticky='ew', padx=16, pady=(16, 4))
        self.detail_tabs = ctk.CTkTabview(self.sidebar, fg_color='transparent')
        self.detail_tabs.grid(row=1, column=0, sticky='nsew', padx=8, pady=(0, 8))
        for name in ('片段', '分析', '版本'):
            tab = self.detail_tabs.add(name)
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(0, weight=1)
        self.segment_list = ctk.CTkScrollableFrame(self.detail_tabs.tab('片段'), fg_color='transparent')
        self.segment_list.grid(row=0, column=0, sticky='nsew')
        self.segment_pages = self._pager(self.detail_tabs.tab('片段'), self._change_segment_page)
        self.match_list = ctk.CTkScrollableFrame(self.detail_tabs.tab('分析'), fg_color='transparent')
        self.match_list.grid(row=0, column=0, sticky='nsew')
        self.match_pages = self._pager(self.detail_tabs.tab('分析'), self._change_match_page)
        self.version_list = ctk.CTkScrollableFrame(self.detail_tabs.tab('版本'), fg_color='transparent')
        self.version_list.grid(row=0, column=0, sticky='nsew')
        self.bind('<Configure>', self._on_resize)
        self._search_matches = []
        self._search_index = -1
        self.set_busy(False)

    def _button(self, parent, text, command, width=70, primary=False):
        return ctk.CTkButton(
            parent, text=text, command=command, width=width, height=32,
            font=AppFonts.BUTTON, fg_color=AppColors.PRIMARY if primary else 'transparent',
            hover_color=AppColors.PRIMARY_HOVER if primary else AppColors.SURFACE,
            text_color='white' if primary else AppColors.TEXT_PRIMARY,
            border_width=0 if primary else 1, border_color=AppColors.BORDER,
        )

    def _text(self, parent, editable=False):
        widget = ctk.CTkTextbox(parent, wrap='word', font=(AppFonts.FAMILY, self._font_size),
                               fg_color=AppColors.SURFACE_RAISED, border_width=0, corner_radius=6)
        widget.tag_config('line_spacing', spacing2=6, spacing3=10)
        widget.tag_config('search', background='#FDE68A', foreground='#1F2937')
        widget.tag_config('current', background='#F59E0B', foreground='#1F2937')
        widget.tag_config('evidence', background='#DBEAFE', foreground='#1E3A8A')
        widget.configure(state='normal' if editable else 'disabled')
        return widget

    def _call(self, name, *args):
        callback = self.callbacks.get(name)
        if callback:
            callback(*args)

    def _rename(self):
        self._call('rename', self.title_entry.get())

    def _replace(self, widget, text, editable=False):
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('1.0', text, 'line_spacing')
        widget.configure(state='normal' if editable else 'disabled')

    def show_document(self, document, revisions, audio_available=False, audio_hint=None):
        self._loading = True
        self.cancel_edit_timer()
        if self._raw_session != document.session_id:
            self._segment_page = self._match_page = 0
            self.scroll_lock_var.set(False)
        self.document = document
        self._revisions = list(revisions)
        self._segments = list(document.segments)
        self._audio_available = audio_available
        self._raw_session = document.session_id
        self.title_entry.configure(state='normal')
        self.title_entry.delete(0, 'end')
        self.title_entry.insert(0, document.title)
        self.title_entry.configure(state='disabled' if self._busy else 'normal')
        self._replace(self.raw_text, document.raw_text)
        self._confirmed = document.raw_text
        self.raw_text._textbox.mark_set('confirmed_end', 'end-1c')
        self.raw_text._textbox.mark_gravity('confirmed_end', 'left')
        self._replace(self.draft_text, document.formatted_text, editable=not self._busy)
        self.draft_text._textbox.edit_reset()
        self.draft_text._textbox.edit_modified(False)
        self.document_info.configure(text=f'原文 {len(document.raw_text)} 字 · 整理稿 {len(document.formatted_text)} 字')
        self.warning_label.configure(text='\n'.join(document.processing_warnings))
        self.warning_label.grid() if document.processing_warnings else self.warning_label.grid_remove()
        self._render_segments()
        self._render_matches()
        self._render_versions()
        self.audio_slider.configure(to=max(1, document.duration_seconds), state='normal' if audio_available and not self._busy else 'disabled')
        self.play_btn.configure(state='normal' if audio_available and not self._busy else 'disabled')
        self.stop_audio_btn.configure(state='normal' if audio_available else 'disabled')
        self.audio_hint.configure(text=audio_hint or ('点击片段回听 · 句级时间为估计值' if audio_available else '此会话未保存音频，或录音文件不可用'))
        self.tabs.set('整理稿' if document.formatted_text else '原始转录')
        self._loading = False
        self.set_busy(self._busy)
        self._on_tab()

    def render_live(self, confirmed, partial, segments):
        widget = self.raw_text
        follow = not self.scroll_lock_var.get()
        position = widget.yview()
        widget.configure(state='normal')
        if confirmed.startswith(self._confirmed):
            widget.delete('confirmed_end', 'end-1c')
            widget.insert('end-1c', confirmed[len(self._confirmed):], 'line_spacing')
        else:
            widget.delete('1.0', 'end')
            widget.insert('1.0', confirmed, 'line_spacing')
        widget._textbox.mark_set('confirmed_end', 'end-1c')
        widget._textbox.mark_gravity('confirmed_end', 'left')
        widget.insert('end-1c', partial, ('partial', 'line_spacing'))
        widget.configure(state='disabled')
        self._confirmed = confirmed
        if follow:
            widget.see('end')
        elif position:
            widget.yview_moveto(position[0])
        self.document_info.configure(text=f'已确认 {len(confirmed.strip())} 字 · {len(segments)} 个片段')
        self._segments = list(segments)
        if len(segments) != getattr(self, '_segment_count', -1):
            self._render_segments()
        if self.search_entry.get() and self._search_timer is None:
            self._search_timer = self.after(180, self.search)

    def get_draft(self):
        return self.draft_text.get('1.0', 'end-1c')

    def cancel_edit_timer(self):
        if self._edit_timer:
            self.after_cancel(self._edit_timer)
            self._edit_timer = None

    def _on_edit(self, event=None):
        if not self.draft_text._textbox.edit_modified():
            return
        self.draft_text._textbox.edit_modified(False)
        if self._loading or self._busy:
            return
        self.cancel_edit_timer()
        self._edit_timer = self.after(600, self._notify_edit)

    def _notify_edit(self):
        self._edit_timer = None
        self._call('draft', self.get_draft())
        if self.document:
            self.document_info.configure(text=f'原文 {len(self.document.raw_text)} 字 · 整理稿 {len(self.get_draft())} 字')
        self._schedule_search()

    def _undo(self, redo):
        try:
            self.draft_text._textbox.edit_redo() if redo else self.draft_text._textbox.edit_undo()
        except tk.TclError:
            pass
        self.tabs.set('整理稿')

    def _on_tab(self):
        if self.tabs.get() == '对照' and self.document:
            edited = self.get_draft()
            self._replace(self.compare_raw, self.document.raw_text)
            self._replace(self.compare_draft, edited)
            for tag, start, end, other_start, other_end in changed_ranges(self.document.raw_text, edited):
                if end > start:
                    self.compare_raw.tag_add('changed', f'1.0+{start}c', f'1.0+{end}c')
                if other_end > other_start:
                    self.compare_draft.tag_add('changed', f'1.0+{other_start}c', f'1.0+{other_end}c')
        self.search()

    def _pager(self, parent, callback):
        footer = ctk.CTkFrame(parent, fg_color='transparent')
        footer.grid(row=1, column=0, sticky='ew', pady=4)
        self._button(footer, '上一页', lambda: callback(-1), width=65).pack(side='left')
        label = ctk.CTkLabel(footer, text='', font=AppFonts.BODY_SMALL)
        label.pack(side='left', expand=True)
        self._button(footer, '下一页', lambda: callback(1), width=65).pack(side='right')
        return label

    def _empty(self, frame, text):
        for child in frame.winfo_children():
            child.destroy()
        if text:
            ctk.CTkLabel(frame, text=text, wraplength=225, justify='left', text_color=AppColors.TEXT_SECONDARY).pack(anchor='w', padx=4, pady=12)

    def _render_segments(self):
        segments = self._segments
        self._segment_count = len(segments)
        self._segment_page = min(self._segment_page, max(0, (len(segments) - 1) // 40))
        self._empty(self.segment_list, '录音确认的句子将在这里出现。\n旧会话没有片段数据时，可使用底部播放器回听。' if not segments else '')
        for index in range(self._segment_page * 40, min(len(segments), (self._segment_page + 1) * 40)):
            segment = segments[index]
            excerpt = segment.text[:55] + ('…' if len(segment.text) > 55 else '')
            text = f'约 {clock_text(segment.start_time)}  →  {clock_text(segment.end_time)}\n{excerpt}'
            self._card(self.segment_list, text, lambda i=index: self._select_segment(i))
        self.segment_pages.configure(text=f'{self._segment_page + 1}/{max(1, (len(segments) + 39) // 40)}')

    def _select_segment(self, index):
        if not self.document:
            return
        ranges = segment_ranges(self.document.raw_text, self._segments)
        start, end = ranges[index]
        self.tabs.set('原始转录')
        self.raw_text.tag_remove('evidence', '1.0', 'end')
        if start >= 0:
            self.raw_text.tag_add('evidence', f'1.0+{start}c', f'1.0+{end}c')
            self.raw_text.see(f'1.0+{start}c')
        self.scroll_lock_var.set(True)
        if not self._busy:
            self._call('seek', max(0, self._segments[index].start_time - 0.5), True)

    def _render_matches(self):
        matches = self.document.behavior_matches if self.document else []
        self._match_page = min(self._match_page, max(0, (len(matches) - 1) // 20))
        self._empty(self.match_list, '使用“行为分析”整理后，可在这里查看模型评分与引文依据。' if not matches else '')
        for index in range(self._match_page * 20, min(len(matches), (self._match_page + 1) * 20)):
            match = matches[index]
            text = f'{match.behavior_name[:20]} · 模型评分 {match.confidence:.0%}\n{match.original_text[:55]}'
            self._card(self.match_list, text, lambda i=index: self._show_evidence(i))
        self.match_pages.configure(text=f'{self._match_page + 1}/{max(1, (len(matches) + 19) // 20)}')

    def _card(self, parent, text, command):
        card = ctk.CTkButton(parent, text=text, anchor='w', height=104, font=AppFonts.BODY,
                             bg_color=AppColors.SURFACE_RAISED,
                             fg_color=AppColors.SURFACE, text_color=AppColors.TEXT_PRIMARY,
                             hover_color=AppColors.BORDER, command=command)
        card._text_label.configure(wraplength=210, justify='left')
        card.pack(fill='x', pady=4)

    def _show_evidence(self, index):
        match = self.document.behavior_matches[index]
        window = ctk.CTkToplevel(self)
        window.title('分析依据')
        window.geometry('720x460')
        window.transient(self.winfo_toplevel())
        ctk.CTkLabel(window, text=f'{match.behavior_name} · 模型评分 {match.confidence:.0%}', font=AppFonts.TITLE).pack(anchor='w', padx=20, pady=(16, 4))
        source = self.document.analysis_text
        ctk.CTkLabel(window, text='以下为本次分析使用的文本；人工修订稿单独保存。' if source else '旧会话未保存分析输入，以下仅显示模型引用。', text_color=AppColors.TEXT_SECONDARY).pack(anchor='w', padx=20, pady=(0, 12))
        view = self._text(window)
        view.pack(fill='both', expand=True, padx=20, pady=(0, 20))
        self._replace(view, source or match.original_text)
        if source and source[match.context_start:match.context_end] == match.original_text:
            view.tag_add('evidence', f'1.0+{match.context_start}c', f'1.0+{match.context_end}c')
            view.see(f'1.0+{match.context_start}c')

    def _render_versions(self):
        self._empty(self.version_list, '保存修订或重新整理后，版本会保留在这里。' if not self._revisions else '')
        for revision in reversed(self._revisions):
            self._button(self.version_list, f"{revision['label']} · {revision['created_at'][5:16].replace('T', ' ')}",
                         lambda identity=revision['id']: self._call('restore_version', identity), width=220).pack(fill='x', pady=4)

    def refresh_revisions(self, revisions):
        self._revisions = list(revisions)
        self._render_versions()

    def show_processing(self, message, cancellable=False):
        self.processing_bar.stop()
        if message is None:
            self.processing_frame.grid_remove()
            return
        self.processing_label.configure(text=message)
        self.cancel_processing_btn.configure(state='normal' if cancellable else 'disabled')
        self.processing_frame.grid()
        self.processing_bar.start()

    def _change_segment_page(self, direction):
        self._segment_page = max(0, self._segment_page + direction)
        self._render_segments()

    def _change_match_page(self, direction):
        self._match_page = max(0, self._match_page + direction)
        self._render_matches()

    def _on_resize(self, event):
        compact = event.width < 980
        if compact != self._last_compact:
            self._last_compact = compact
            self._set_sidebar(not compact)

    def _set_sidebar(self, visible):
        self._sidebar_visible = visible
        self.sidebar.grid() if visible else self.sidebar.grid_remove()
        self.details_btn.configure(text='收起侧栏' if visible else '核查与版本')

    def toggle_sidebar(self):
        self._set_sidebar(not self._sidebar_visible)

    def _check_scroll(self):
        position = self.raw_text.yview()
        if position:
            self.scroll_lock_var.set(position[1] < 0.98)

    def follow_latest(self):
        self.scroll_lock_var.set(False)
        self.tabs.set('原始转录')
        self.raw_text.see('end')

    def search_target(self):
        return {'整理稿': self.draft_text, '对照': self.compare_draft}.get(self.tabs.get(), self.raw_text)

    def _schedule_search(self, event=None):
        if self._search_timer:
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(180, self.search)

    def search(self):
        if self._search_timer:
            self.after_cancel(self._search_timer)
        self._search_timer = None
        widget = self.search_target()
        for candidate in (self.raw_text, self.draft_text, self.compare_draft):
            candidate.tag_remove('search', '1.0', 'end')
            candidate.tag_remove('current', '1.0', 'end')
        self._search_matches = []
        term = self.search_entry.get()
        start = '1.0'
        if term:
            while True:
                found = widget._textbox.search(term, start, stopindex='end', nocase=True, exact=True)
                if not found:
                    break
                end = f'{found}+{len(term)}c'
                widget.tag_add('search', found, end)
                self._search_matches.append((found, end))
                start = end
        self._search_index = -1
        self.search_count.configure(text=str(len(self._search_matches)) if term else '')

    def search_next(self, direction=1):
        if not self._search_matches:
            self.search()
        if self._search_matches:
            self._search_index = (self._search_index + direction) % len(self._search_matches)
            start, end = self._search_matches[self._search_index]
            widget = self.search_target()
            widget.tag_remove('current', '1.0', 'end')
            widget.tag_add('current', start, end)
            widget.see(start)
            self.search_count.configure(text=f'{self._search_index + 1}/{len(self._search_matches)}')

    def set_busy(self, busy):
        self._busy = busy
        editable = self.document is not None and not busy
        for widget in (self.commit_btn, self.undo_btn, self.redo_btn,
                       self.reprocess_btn, self.reanalyze_btn, self.title_entry, self.rename_btn):
            widget.configure(state='normal' if editable else 'disabled')
        self.draft_text.configure(state='normal' if editable else 'disabled')
        for widget in (self.play_btn, self.stop_audio_btn, self.audio_slider):
            widget.configure(state='normal' if self._audio_available and not busy else 'disabled')

    def update_playback(self, playing, position, duration):
        self.play_btn.configure(text='暂停' if playing else '播放')
        if self._dragging_audio:
            return
        self.audio_slider.configure(to=max(1, duration))
        self.audio_slider.set(position)
        self.audio_time.configure(text=f'{clock_text(position)} / {clock_text(duration)}')

    def _preview_seek(self, seconds):
        self.audio_time.configure(text=f'{clock_text(seconds)} / {clock_text(self.audio_slider.cget("to"))}')

    def refresh_theme(self):
        color = AppColors.TEXT_SECONDARY[0 if ctk.get_appearance_mode() == 'Light' else 1]
        self.raw_text.tag_config('partial', foreground=color)

    def _begin_seek(self, event=None):
        self._dragging_audio = True

    def _finish_seek(self, event=None):
        self._dragging_audio = False
        self._call('seek', self.audio_slider.get(), False)

    def set_font_size(self, size):
        self._font_size = size
        for widget in (self.raw_text, self.draft_text, self.compare_raw, self.compare_draft):
            widget.configure(font=(AppFonts.FAMILY, size))
