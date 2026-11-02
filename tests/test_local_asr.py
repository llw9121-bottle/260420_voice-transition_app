"""本地 ASR 客户端单元测试；使用 fake sherpa 模块，不下载真实模型。"""

import subprocess
import sys
import time
import types
from pathlib import Path
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


class FakeStream:
    def __init__(self):
        self.text = ''
        self.ready = False
        self.endpoint = False
        self.finished = False
        self.accepted = 0

    def accept_waveform(self, sample_rate, samples):
        self.accepted += len(samples)
        self.ready = True
        if np.any(samples):
            self.text = '第一句'

    def input_finished(self):
        self.finished = True
        self.ready = True

    def reset(self):
        self.text = ''
        self.ready = False
        self.endpoint = False


class FakeRecognizer:
    def __init__(self, endpoint_after=1, delay=0.0):
        self.endpoint_after = endpoint_after
        self.delay = delay
        self.stream = FakeStream()
        self.decode_calls = 0

    def create_stream(self):
        return self.stream

    def is_ready(self, stream):
        return stream.ready

    def decode_stream(self, stream):
        if self.delay:
            time.sleep(self.delay)
        stream.ready = False
        self.decode_calls += 1
        if self.endpoint_after is not None and self.decode_calls >= self.endpoint_after:
            stream.endpoint = True

    def get_result(self, stream):
        # 与 sherpa-onnx 2.x 一致：返回纯字符串。
        return stream.text

    def is_endpoint(self, stream):
        return stream.endpoint

    def reset(self, stream):
        stream.reset()
        self.decode_calls = 0


def _install_fake_sherpa(monkeypatch, recognizer):
    module = types.SimpleNamespace(
        OnlineRecognizer=types.SimpleNamespace(from_paraformer=lambda **kwargs: recognizer)
    )
    monkeypatch.setattr(local_asr, '_load_sherpa', lambda: module)


def _write_model_files(directory: Path) -> None:
    for name in ('encoder.int8.onnx', 'decoder.int8.onnx', 'tokens.txt'):
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
    config.language = 'ja'
    client = LocalASRClient(config, model_dir=tmp_path)
    assert client.start() is False
    assert '仅支持中文' in client.last_error


def test_partial_endpoint_and_final_order(tmp_path, monkeypatch):
    _write_model_files(tmp_path)
    _install_fake_sherpa(monkeypatch, FakeRecognizer(endpoint_after=1))

    calls = []
    client = LocalASRClient(FakeConfig(), model_dir=tmp_path)
    assert client.start(
        on_partial=lambda text: calls.append(('partial', text)),
        on_final=lambda text: calls.append(('final', text)),
        on_speech_start=lambda: calls.append(('start', None)),
        on_speech_stop=lambda: calls.append(('stop', None)),
    )
    assert client.send_audio(_audio_chunk())
    client.stop()

    assert calls == [
        ('start', None),
        ('partial', '第一句'),
        ('stop', None),
        ('final', '第一句'),
    ]


def test_stop_flushes_last_sentence_without_endpoint(tmp_path, monkeypatch):
    _write_model_files(tmp_path)
    _install_fake_sherpa(monkeypatch, FakeRecognizer(endpoint_after=None))

    finals = []
    client = LocalASRClient(FakeConfig(), model_dir=tmp_path)
    assert client.start(on_final=finals.append)
    assert client.send_audio(_audio_chunk())
    assert client.stop() is True

    assert finals == ['第一句']
    assert client.get_transcription() == '第一句'


def test_stop_is_idempotent(tmp_path, monkeypatch):
    _write_model_files(tmp_path)
    _install_fake_sherpa(monkeypatch, FakeRecognizer(endpoint_after=None))

    finals = []
    client = LocalASRClient(FakeConfig(), model_dir=tmp_path)
    assert client.start(on_final=finals.append)
    assert client.send_audio(_audio_chunk())

    assert client.stop() is True
    assert client.stop() is True
    assert finals == ['第一句']


def test_send_after_stop_returns_false(tmp_path, monkeypatch):
    _write_model_files(tmp_path)
    _install_fake_sherpa(monkeypatch, FakeRecognizer(endpoint_after=None))

    client = LocalASRClient(FakeConfig(), model_dir=tmp_path)
    assert client.start()
    assert client.stop() is True
    assert client.send_audio(_audio_chunk()) is False


def test_stop_is_bounded_when_decode_blocks(tmp_path, monkeypatch):
    _write_model_files(tmp_path)
    _install_fake_sherpa(monkeypatch, FakeRecognizer(endpoint_after=None, delay=0.3))

    client = LocalASRClient(FakeConfig(), model_dir=tmp_path)
    assert client.start()
    assert client.send_audio(_audio_chunk())

    started = time.monotonic()
    assert client.stop(timeout=0.05) is False
    assert time.monotonic() - started < 1.0
    assert '时限' in client.last_error

    # 解码和收尾各执行一次延时，等待后台线程自然退出。
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
