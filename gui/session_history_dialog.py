"""搜索并打开本地持久会话。"""

import customtkinter as ctk

from core.review import clock_text
from gui.theme import AppColors, AppFonts


class SessionHistoryDialog(ctk.CTkToplevel):
    def __init__(self, parent, rows, on_open):
        super().__init__(parent)
        self.title('会话历史')
        self.geometry('680x560')
        self.minsize(520, 400)
        self.transient(parent)
        self._rows = rows
        self._on_open = on_open
        self._page = 0
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.search = ctk.CTkEntry(self, placeholder_text='搜索标题或原文', height=38)
        self.search.grid(row=0, column=0, sticky='ew', padx=20, pady=20)
        self.search.bind('<KeyRelease>', lambda event: self._filter())
        self.results = ctk.CTkScrollableFrame(self, fg_color='transparent')
        self.results.grid(row=1, column=0, sticky='nsew', padx=16)
        footer = ctk.CTkFrame(self, fg_color='transparent')
        footer.grid(row=2, column=0, sticky='ew', padx=20, pady=16)
        ctk.CTkButton(footer, text='上一页', width=80, command=lambda: self._turn(-1)).pack(side='left')
        self.count = ctk.CTkLabel(footer, text='')
        self.count.pack(side='left', expand=True)
        ctk.CTkButton(footer, text='下一页', width=80, command=lambda: self._turn(1)).pack(side='right')
        self._render()

    def _filter(self):
        self._page = 0
        self._render()

    def _turn(self, direction):
        self._page = max(0, self._page + direction)
        self._render()

    def _render(self):
        term = self.search.get().strip().casefold()
        rows = [row for row in self._rows if term in row['search_text'].casefold()]
        self._page = min(self._page, max(0, (len(rows) - 1) // 30))
        for child in self.results.winfo_children():
            child.destroy()
        if not rows:
            ctk.CTkLabel(self.results, text='没有找到会话。', text_color=AppColors.TEXT_SECONDARY).pack(pady=30)
        for row in rows[self._page * 30:(self._page + 1) * 30]:
            text = f"{row['title']}\n{row['created_at'][:16].replace('T', ' ')} · {clock_text(row['duration_seconds'])} · {row['word_count']} 字"
            ctk.CTkButton(self.results, text=text, height=68, anchor='w', font=AppFonts.BODY,
                         fg_color=AppColors.SURFACE, text_color=AppColors.TEXT_PRIMARY,
                         hover_color=AppColors.BORDER, command=lambda identity=row['session_id']: self._open(identity)).pack(fill='x', pady=5)
        self.count.configure(text=f'共 {len(rows)} 个会话 · {self._page + 1}/{max(1, (len(rows) + 29) // 30)}')

    def _open(self, session_id):
        self._on_open(session_id)
        self.destroy()
