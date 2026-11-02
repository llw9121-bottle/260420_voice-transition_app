"""后台流式 WAV 回放；播放、定位与停止不会阻塞 Tk 主线程。"""

import threading
import wave
from pathlib import Path
from queue import Empty, Queue

import pyaudio

from utils.logger import logger


class AudioPlayer:
    def __init__(self):
        self._commands = Queue(maxsize=1)
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._closed = threading.Event()
        self._worker = None
        self._generation = 0
        self._state = {'playing': False, 'position': 0.0, 'duration': 0.0, 'error': None}

    def state(self) -> dict:
        with self._lock:
            return dict(self._state)

    def _publish(self, generation, **updates):
        with self._lock:
            if generation == self._generation:
                self._state.update(updates)

    def play(self, path: Path, seconds: float = 0):
        with self._lock:
            if self._closed.is_set():
                return
            self._cancel.set()
            self._generation += 1
            generation = self._generation
            cancel = self._cancel = threading.Event()
            self._state.update(playing=True, position=max(0, seconds), error=None)
            try:
                self._commands.get_nowait()
            except Empty:
                pass
            self._commands.put_nowait((generation, Path(path), max(0, seconds), cancel))
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name='audio-playback', daemon=True)
                self._worker.start()

    def stop(self, reset=False):
        with self._lock:
            self._cancel.set()
            self._generation += 1
            self._state['playing'] = False
            self._state['error'] = None
            if reset:
                self._state['position'] = 0.0
                self._state['duration'] = 0.0
            try:
                self._commands.get_nowait()
            except Empty:
                pass

    def close(self, wait=False):
        self._closed.set()
        self.stop()
        if wait and self._worker:
            self._worker.join(timeout=3)

    def _run(self):
        while not self._closed.is_set():
            try:
                generation, path, seconds, cancel = self._commands.get(timeout=0.1)
            except Empty:
                continue
            if cancel.is_set():
                continue
            stream = audio = None
            try:
                with wave.open(str(path), 'rb') as wav:
                    rate = wav.getframerate()
                    duration = wav.getnframes() / rate
                    frame = min(int(seconds * rate), wav.getnframes())
                    wav.setpos(frame)
                    self._publish(generation, position=frame / rate, duration=duration)
                    audio = pyaudio.PyAudio()
                    stream = audio.open(
                        format=audio.get_format_from_width(wav.getsampwidth()),
                        channels=wav.getnchannels(), rate=rate, output=True,
                    )
                    while not cancel.is_set() and not self._closed.is_set():
                        data = wav.readframes(1024)
                        if not data:
                            break
                        stream.write(data)
                        self._publish(generation, position=wav.tell() / rate)
            except Exception as error:
                self._publish(generation, error=str(error))
            finally:
                if stream:
                    for release in (stream.stop_stream, stream.close):
                        try:
                            release()
                        except Exception as error:
                            logger.debug(f'释放音频流资源失败: {error}')
                if audio:
                    try:
                        audio.terminate()
                    except Exception as error:
                        self._publish(generation, error=str(error))
                self._publish(generation, playing=False)
