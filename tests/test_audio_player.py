"""使用虚拟输出设备验证回放与取消，不触碰真实声卡。"""

import threading
import time
import wave
from unittest.mock import Mock

import pytest

from core.audio_player import AudioPlayer


def wait_for(predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert predicate()


@pytest.fixture
def wav_file(tmp_path):
    path = tmp_path / 'audio.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\x00\x00' * 32000)
    return path


def test_seek_streams_from_requested_frame_and_releases_resources(wav_file, monkeypatch):
    output = Mock()
    audio = Mock()
    audio.open.return_value = output
    monkeypatch.setattr('core.audio_player.pyaudio.PyAudio', lambda: audio)
    player = AudioPlayer()
    try:
        player.play(wav_file, 1.5)
        wait_for(lambda: not player.state()['playing'])
        assert sum(len(call.args[0]) for call in output.write.call_args_list) == 16000
        assert player.state()['position'] == 2
        assert player.state()['duration'] == 2
        output.close.assert_called_once()
        audio.terminate.assert_called_once()
    finally:
        player.close(wait=True)


def test_cancelled_generation_cannot_overwrite_reset_position(wav_file, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    output, audio = Mock(), Mock()
    def write(data):
        entered.set()
        assert release.wait(2)
    output.write.side_effect = write
    audio.open.return_value = output
    monkeypatch.setattr('core.audio_player.pyaudio.PyAudio', lambda: audio)
    player = AudioPlayer()
    try:
        player.play(wav_file, 1)
        assert entered.wait(2)
        player.stop(reset=True)
        release.set()
        wait_for(lambda: output.close.called)
        assert player.state() == {'playing': False, 'position': 0.0, 'duration': 0.0, 'error': None}
    finally:
        release.set()
        player.close(wait=True)


def test_missing_file_and_cleanup_failure_allow_retry(wav_file, monkeypatch):
    audio = Mock()
    audio.terminate.side_effect = OSError('输出设备已移除')
    audio.open.return_value.stop_stream.side_effect = OSError('停止失败')
    monkeypatch.setattr('core.audio_player.pyaudio.PyAudio', lambda: audio)
    player = AudioPlayer()
    try:
        player.play(wav_file.with_name('missing.wav'))
        wait_for(lambda: not player.state()['playing'])
        assert player.state()['error']
        player.play(wav_file)
        wait_for(lambda: not player.state()['playing'])
        assert player.state()['error'] == '输出设备已移除'
        audio.open.return_value.close.assert_called_once()
        audio.terminate.side_effect = None
        player.play(wav_file, 2)
        wait_for(lambda: not player.state()['playing'])
        assert player.state()['error'] is None
    finally:
        player.close(wait=True)
