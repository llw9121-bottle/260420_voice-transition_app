"""
实时字幕显示组件

提供滚动文本框显示实时转录内容。
支持追加模式和覆盖模式。
"""

import customtkinter as ctk
from typing import Optional


class TranscriptionView:
    """
    转录文本显示组件
    
    提供滚动文本框显示实时转录内容。
    """
    
    def __init__(self, parent: ctk.CTkFrame):
        """
        初始化显示组件
        
        Args:
            parent: 父框架
        """
        self.parent = parent
        
        # 创建主框架
        self.frame = ctk.CTkFrame(parent)
        self.frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 标题栏
        self.header = ctk.CTkFrame(self.frame, fg_color="transparent", height=30)
        self.header.pack(fill="x", padx=10, pady=(5, 0))
        self.header.pack_propagate(False)
        
        self.title_label = ctk.CTkLabel(
            self.header,
            text="实时转录",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.title_label.pack(side="left")
        
        # 字数统计
        self.word_count_label = ctk.CTkLabel(
            self.header,
            text="字数: 0",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.word_count_label.pack(side="right", padx=10)
        
        # 文本框容器（用于添加内边距）
        self.text_container = ctk.CTkFrame(self.frame)
        self.text_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 文本框
        self.text_widget = ctk.CTkTextbox(
            self.text_container,
            wrap="word",
            font=ctk.CTkFont(size=13),
            activate_scrollbars=True
        )
        self.text_widget.pack(fill="both", expand=True)
        
        # 设置文本框样式
        self.text_widget.configure(
            fg_color=("#f5f5f5", "#2b2b2b"),
            text_color=("#1a1a1a", "#e5e5e5")
        )
        
        # 初始文本
        self.text_widget.insert("0.0", "等待开始录音...")
        self.text_widget.configure(state="disabled")
        
        # 字数统计
        self.current_word_count = 0
        
    def append_text(self, text: str, is_final: bool = True):
        """
        追加文本到显示区
        
        Args:
            text: 要追加的文本
            is_final: 是否是最终结果（True）或临时结果（False）
        """
        self.text_widget.configure(state="normal")
        
        # 如果当前是初始文本，先清除
        current_text = self.text_widget.get("0.0", "end-1c")
        if current_text == "等待开始录音...":
            self.text_widget.delete("0.0", "end")
        
        # 根据是否是最终结果设置不同的颜色标签
        if is_final:
            self.text_widget.insert("end", text)
        else:
            # 临时结果用灰色显示
            self.text_widget.insert("end", text)
            
        # 更新字数统计
        self._update_word_count(len(text))
        
        self.text_widget.configure(state="disabled")
        self.text_widget.see("end")
        
    def set_text(self, text: str):
        """
        设置（覆盖）文本内容
        
        Args:
            text: 要显示的文本
        """
        self.text_widget.configure(state="normal")
        self.text_widget.delete("0.0", "end")
        self.text_widget.insert("0.0", text)
        self.text_widget.configure(state="disabled")
        
        # 更新字数统计
        self._update_word_count(len(text))
        
    def clear(self):
        """清空文本内容"""
        self.text_widget.configure(state="normal")
        self.text_widget.delete("0.0", "end")
        self.text_widget.insert("0.0", "等待开始录音...")
        self.text_widget.configure(state="disabled")
        
        # 重置字数统计
        self._update_word_count(0)
        
    def _update_word_count(self, added_count: int):
        """
        更新字数统计
        
        Args:
            added_count: 新增的字数
        """
        self.current_word_count += added_count
        self.word_count_label.configure(text=f"字数: {self.current_word_count}")
        
    def get_text(self) -> str:
        """
        获取当前文本内容
        
        Returns:
            当前显示的文本
        """
        return self.text_widget.get("0.0", "end-1c")
        
    def enable(self):
        """启用文本框"""
        self.text_widget.configure(state="normal")
        
    def disable(self):
        """禁用文本框"""
        self.text_widget.configure(state="disabled")


# 测试代码
if __name__ == "__main__":
    import time
    import threading
    
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    
    root = ctk.CTk()
    root.title("转录显示测试")
    root.geometry("800x600")
    
    view = TranscriptionView(root)
    view.frame.pack(fill="both", expand=True, padx=10, pady=10)
    
    # 模拟实时转录
    def simulate_transcription():
        time.sleep(1)
        
        texts = [
            "大家好，",
            "今天我们讨论一下项目进度。",
            "我觉得目前的进展还不错，",
            "但是还有一些问题需要解决。",
        ]
        
        for text in texts:
            root.after(0, lambda t=text: view.append_text(t))
            time.sleep(1.5)
            
    # 启动模拟线程
    thread = threading.Thread(target=simulate_transcription, daemon=True)
    thread.start()
    
    root.mainloop()
