"""整理阶段反馈与协作式取消。已发送的远程请求返回后再检查取消。"""

import threading

from utils.exceptions import ProcessingCancelled


class ProcessingContext:
    def __init__(self, on_progress=None):
        self.cancelled = threading.Event()
        self.on_progress = on_progress

    def cancel(self):
        self.cancelled.set()

    def check(self):
        if self.cancelled.is_set():
            raise ProcessingCancelled()

    def report(self, message):
        self.check()
        if self.on_progress:
            self.on_progress(message)
