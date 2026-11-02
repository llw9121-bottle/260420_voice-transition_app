"""界面与应用共享的录音生命周期。"""

from enum import Enum


class RecordingState(str, Enum):
    READY = 'ready'
    CONNECTING = 'connecting'
    RECORDING = 'recording'
    PAUSED = 'paused'
    RECONNECTING = 'reconnecting'
    STOPPING = 'stopping'
    PROCESSING = 'processing'
    SAVED = 'saved'
    ERROR = 'error'

    @property
    def captures_audio(self) -> bool:
        return self in {self.RECORDING, self.PAUSED, self.RECONNECTING}

    @property
    def busy(self) -> bool:
        return self.captures_audio or self in {self.CONNECTING, self.STOPPING, self.PROCESSING}
