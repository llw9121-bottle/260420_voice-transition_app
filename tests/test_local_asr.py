"""本地 SenseVoice 客户端单元测试；使用 fake sherpa，不下载真实模型。"""

import subprocess
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from api import local_asr
from api.local_asr import LocalASRClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class FakeConfig:
    sample_rate = 16000
    language = 'zh'
    vad_silence_ms = 400
    max_session_duration = 1200


class FakeOfflineStream:
    def __init__(self):
        self.samples = None
        self.result = SimpleNamespace(text='')

    def accept_waveform(self, sample_rate, samples):
        self.samples = np.asarray(samples, dtype=np.float32)


class FakeRecognizer:
    def __init__(self, delay=0.0):
        self.delay = delay

    def create_stream(self):
        return FakeOfflineStream()

    def decode_stream(self, stream):
        if self.delay:
            time.sleep(self.delay)
        # 带 SenseVoice 标签，验证 <|...|> 会被清理。
        stream.result = SimpleNamespace(text='<|zh|><|NEUTRAL|><|Speech|>测试，文本。')


class FakeVad:
    """按 chunk 数触发语音段，便于确定性测试。"""

    def __init__(self, emit_after=2):
        self.emit_after = emit_after
        self.buffer = []
        self.pending = []
        self.active = False
        self.chunks = 0

    def accept_waveform(self, samples):
        self.chunks += 1
        self.buffer.append(np.asarray(samples, dtype=np.float32))
        self.active = True
        if self.chunks >= self.emit_after:
            self.pending.append(np.concatenate(self.buffer))
            self.buffer = []
            self.active = False
            self.chunks = 0

    def is_speech_detected(self):
        return self.active

    @property
    def current_segment(self):
        samples = (
            np.concatenate(self.buffer) if self.buffer
            else np.array([], dtype=np.float32)
        )
        return SimpleNamespace(samples=samples)

    def empty(self):
        return not self.pending

    @property
    def front(self):
        return SimpleNamespace(samples=self.pending[0])

    def pop(self):
        self.pending.pop(0)

    def flush(self):
        if self.buffer:
            self.pending.append(np.concatenate(self.buffer))
            self.buffer = []
        self.active = False


def _install_fake_sherpa(monkeypatch, vad, recognizer):
    module = types.SimpleNamespace(
        OfflineRecognizer=types.SimpleNamespace(
            from_sense_voice=lambda **kwargs: recognizer
        ),
        SileroVadModelConfig=lambda **kwargs: types.SimpleNamespace(**kwargs),
        VadModelConfig=lambda **kwargs: types.SimpleNamespace(**kwargs),
        VoiceActivityDetector=lambda config, buffer_size_in_seconds=60: vad,
    )
    monkeypatch.setattr(local_asr, '_load_sherpa', lambda: module)


def _write_model_files(directory: Path) -> None:
    for name in ('model.int8.onnx', 'tokens.txt', 'silero_vad.onnx'):
        (directory / name).write_bytes(b'')


def _audio_chunk() -> bytes:
    return (np.ones(1024, dtype=np.int16) * 8000).tobytes()


def test_start_fails_with_missing_model(tmp_path):
    client = LocalASRClient(FakeConfig(), model_dir=tmp_path)
    assert client.start() is False
    assert '模型缺失' in client.last_error
    assert str(tmp_path) in client.last_error


def test_start_rejects_unsupported_language(tmp_path):
    _write_model_files(tmp_path)
    config = FakeConfig()
    config.language = 'fr'
    client = LocalASRClient(config, model_dir=tmp_path)
    assert client.start() is False
    assert '仅支持' in client.last_error


def test_segment_emits_start_stop_and_punctuated_final(tmp_path, monkeypatch):
    _write_model_files(tmp_path)
    _install_fake_sherpa(monkeypatch, FakeVad(emit_after=2), FakeRecognizer())

    calls = []
    client = LocalASRClient(FakeConfig(), model_dir=tmp_path)
    assert client.start(
        on_partial=lambda text: calls.append(('partial', text)),
        on_final=lambda text: calls.append(('final', text)),
        on_speech_start=lambda: calls.append(('start', None)),
        on_speech_stop=lambda: calls.append(('stop', None)),
    )
    assert client.send_audio(_audio_chunk())
    assert client.send_audio(_audio_chunk())
    assert client.stop() is True

    assert calls == [
        ('start', None),
        ('stop', None),
        ('final', '测试，文本。'),
    ]


def test_stop_flushes_last_segment(tmp_path, monkeypatch):
    _write_model_files(tmp_path)
    _install_fake_sherpa(monkeypatch, FakeVad(emit_after=999), FakeRecognizer())

    finals = []
    client = LocalASRClient(FakeConfig(), model_dir=tmp_path)
    assert client.start(on_final=finals.append)
    assert client.send_audio(_audio_chunk())
    assert client.stop() is True

    assert finals == ['测试，文本。']
    assert client.get_transcription() == '测试，文本。'


def test_partial_result_is_emitted(tmp_path, monkeypatch):
    _write_model_files(tmp_path)
    _install_fake_sherpa(monkeypatch, FakeVad(emit_after=999), FakeRecognizer())

    partials = []
    client = LocalASRClient(FakeConfig(), model_dir=tmp_path)
    assert client.start(on_partial=partials.append)
    assert client.send_audio(_audio_chunk())
    time.sleep(0.3)

    client._emit_partial()
    client.stop()

    assert partials == ['测试，文本。']


def test_stop_is_idempotent(tmp_path, monkeypatch):
    _write_model_files(tmp_path)
    _install_fake_sherpa(monkeypatch, FakeVad(emit_after=999), FakeRecognizer())

    finals = []
    client = LocalASRClient(FakeConfig(), model_dir=tmp_path)
    assert client.start(on_final=finals.append)
    assert client.send_audio(_audio_chunk())

    assert client.stop() is True
    assert client.stop() is True
    assert finals == ['测试，文本。']


def test_send_after_stop_returns_false(tmp_path, monkeypatch):
    _write_model_files(tmp_path)
    _install_fake_sherpa(monkeypatch, FakeVad(emit_after=999), FakeRecognizer())

    client = LocalASRClient(FakeConfig(), model_dir=tmp_path)
    assert client.start()
    assert client.stop() is True
    assert client.send_audio(_audio_chunk()) is False


def test_stop_is_bounded_when_decode_blocks(tmp_path, monkeypatch):
    _write_model_files(tmp_path)
    _install_fake_sherpa(
        monkeypatch, FakeVad(emit_after=2), FakeRecognizer(delay=0.3)
    )

    client = LocalASRClient(FakeConfig(), model_dir=tmp_path)
    assert client.start()
    assert client.send_audio(_audio_chunk())
    assert client.send_audio(_audio_chunk())

    started = time.monotonic()
    assert client.stop(timeout=0.05) is False
    assert time.monotonic() - started < 1.0
    assert '时限' in client.last_error

    time.sleep(1.0)
    assert client._worker is not None and not client._worker.is_alive()


def test_supports_reconnect_is_false():
    assert LocalASRClient.supports_reconnect is False


def test_import_does_not_load_sherpa():
    code = (
        "import sys; import api.local_asr; "
        "assert 'sherpa_onnx' not in sys.modules; print('ok')"
    )
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert 'ok' in result.stdout
