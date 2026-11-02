"""用假音频设备及假 ASR 验证采集、写盘、发送和收尾。"""

import threading
import time
import wave
from unittest.mock import Mock

import pytest

from core.audio_recorder import AudioConfig, AudioRecorder
from core.realtime_transcriber import RealtimeTranscriber
from api.dashscope_asr import ASRConfig, DashScopeASRClient, RealtimeASRCallback


@pytest.fixture(autouse=True)
def isolated_devices(monkeypatch):
    audio = Mock()
    audio.get_sample_size.return_value = 2
    audio.get_default_input_device_info.return_value = {'index': 0}
    audio.get_device_info_by_index.return_value = {'name': '测试麦克风', 'maxInputChannels': 1}
    monkeypatch.setattr('core.audio_recorder.pyaudio.PyAudio', lambda: audio)
    monkeypatch.setattr('requests.sessions.Session.request', Mock(side_effect=AssertionError('禁止真实 API')))
    monkeypatch.setattr('api.dashscope_asr.OmniRealtimeConversation.connect', Mock(side_effect=AssertionError('禁止真实 ASR')))
    return audio


def feed(recorder, data=b'\x01\x00' * 1024):
    recorder._stream_callback(data, len(data) // 2, {}, 0)
    return data


def test_bounded_capture_never_calls_user_callback_inline():
    recorder = AudioRecorder(AudioConfig(save_audio=False, queue_seconds=0.064))
    recorder.is_recording = True
    callback = recorder.on_audio_callback = Mock()
    for _ in range(5):
        feed(recorder)
    assert recorder.audio_queue.qsize() == 1
    assert recorder.dropped_chunks == 4
    assert recorder.gaps == [{'reason': 'network_buffer_full', 'start_byte': 2048, 'end_byte': 10240}]
    callback.assert_not_called()
    recorder.stop()


def test_audio_spools_to_disk_and_survives_stop(tmp_path):
    recorder = AudioRecorder(audio_path=tmp_path / 'session.wav')
    recorder.start()
    chunks = [feed(recorder) for _ in range(4)]
    recorder.pause()
    feed(recorder)
    recorder.resume()
    chunks.append(feed(recorder))
    recorder.stop()
    assert not recorder._writer_thread.is_alive()
    assert recorder.recorded_frames == []
    assert recorder.get_duration() == pytest.approx(5 * 1024 / 16000)
    with wave.open(str(recorder.audio_path), 'rb') as audio:
        assert audio.readframes(audio.getnframes()) == b''.join(chunks)
    exported = tmp_path / 'export.wav'
    recorder.save_wav(exported)
    assert exported.read_bytes() == recorder.audio_path.read_bytes()


def test_no_audio_save_still_tracks_duration_and_retains_network_tail():
    recorder = AudioRecorder(AudioConfig(save_audio=False))
    recorder.start()
    feed(recorder)
    recorder.stop()
    assert recorder.audio_path is None
    assert recorder.get_duration() == pytest.approx(1024 / 16000)
    assert recorder.get_audio_data(timeout=0) is not None


def test_callback_dispatches_on_worker_thread():
    recorder = AudioRecorder(AudioConfig(save_audio=False))
    callback_thread = []
    done = threading.Event()
    def callback(data):
        callback_thread.append(threading.get_ident())
        done.set()
    recorder.start(on_audio=callback)
    feed(recorder)
    assert done.wait(2)
    recorder.stop()
    assert callback_thread != [threading.get_ident()]
    assert not recorder._callback_thread.is_alive()


def test_disk_failure_is_reported_and_writer_exits(tmp_path, monkeypatch):
    original = wave.Wave_write.writeframes
    def fail_on_data(writer, data):
        if data:
            raise OSError('磁盘已满')
        return original(writer, data)
    monkeypatch.setattr(wave.Wave_write, 'writeframes', fail_on_data)
    recorder = AudioRecorder(audio_path=tmp_path / 'session.wav')
    recorder.start()
    feed(recorder)
    recorder.stop()
    assert recorder.write_error == '磁盘已满'
    assert not recorder._writer_thread.is_alive()


def test_writer_queue_overflow_is_bounded_and_reported(tmp_path, monkeypatch):
    release = threading.Event()
    recorder = AudioRecorder(AudioConfig(writer_queue_seconds=0.064), audio_path=tmp_path / 'session.wav')
    def blocked_writer():
        recorder._writer_ready.set()
        release.wait(2)
    monkeypatch.setattr(recorder, '_write_audio', blocked_writer)
    recorder.start()
    for _ in range(5):
        feed(recorder)
    assert recorder._writer_queue.qsize() == 1
    assert recorder.write_dropped_chunks == 4
    assert recorder.gaps[-1]['reason'] == 'audio_writer_full'
    release.set()
    recorder.stop()


def test_audio_open_failure_releases_writer(tmp_path, isolated_devices):
    isolated_devices.open.side_effect = OSError('设备不可用')
    recorder = AudioRecorder(audio_path=tmp_path / 'session.wav')
    with pytest.raises(Exception, match='设备不可用'):
        recorder.start()
    assert not recorder.is_recording
    assert not recorder._writer_thread.is_alive()


@pytest.fixture
def fake_asr(monkeypatch):
    client = Mock()
    client.start.return_value = True
    client.send_audio.return_value = True
    monkeypatch.setattr('core.realtime_transcriber.DashScopeASRClient', lambda config: client)
    return client


def test_start_failure_cleans_up_and_can_retry(fake_asr):
    fake_asr.start.return_value = False
    transcriber = RealtimeTranscriber(save_audio=False)
    assert transcriber.start() is False
    assert not transcriber.is_recording()
    assert transcriber.asr_client is None
    assert transcriber.last_error
    fake_asr.start.return_value = True
    assert transcriber.start()
    transcriber.stop()


def test_stop_preserves_final_and_partial_results(fake_asr):
    transcriber = RealtimeTranscriber(save_audio=False)
    assert transcriber.start()
    transcriber._on_asr_final('第一句')
    transcriber._on_asr_partial('最后一句')
    result = transcriber.stop()
    assert result == '第一句 最后一句'
    assert transcriber.get_transcription() == result
    assert transcriber.stop() == result
    assert not transcriber._sender_thread.is_alive()
    assert [segment.text for segment in transcriber.segments] == ['第一句', '最后一句']


def test_chunk_offsets_exclude_pause_and_survive_queue_delay():
    recorder = AudioRecorder(AudioConfig(save_audio=False))
    recorder.start()
    first = feed(recorder)
    recorder.pause()
    feed(recorder)
    recorder.resume()
    feed(recorder)
    chunks = [recorder.get_audio_chunk(timeout=0), recorder.get_audio_chunk(timeout=0)]
    recorder.stop()
    assert [chunk.start_byte for chunk in chunks] == [0, len(first)]
    assert chunks[0].data == first


def test_sentence_times_use_sent_audio_position_not_capture_tail(fake_asr):
    transcriber = RealtimeTranscriber(save_audio=False)
    transcriber.recorder.get_duration = Mock(return_value=10)
    transcriber._sent_start, transcriber._sent_end = 1, 2
    transcriber._on_speech_start()
    transcriber._on_speech_stop()
    transcriber._sent_end = 5  # 识别延迟期间又发送了后续音频。
    callback = transcriber.on_segment = Mock()
    transcriber._on_asr_final('第一句')
    first = transcriber.segments[0]
    assert (first.start_time, first.end_time) == (1, 2)
    assert first.timing_source == 'estimated'
    transcriber._speech_start, transcriber._speech_end = 1, 50
    transcriber._on_asr_final('第二句')
    assert (transcriber.segments[1].start_time, transcriber.segments[1].end_time) == (2, 10)
    assert callback.call_count == 2


def test_stop_includes_final_result_arriving_during_end_session(fake_asr):
    transcriber = RealtimeTranscriber(save_audio=False)
    transcriber.start()
    transcriber._on_asr_partial('临时')
    fake_asr.stop.side_effect = lambda: transcriber._on_asr_final('确认文本')
    assert transcriber.stop() == '确认文本'


def test_blocked_network_does_not_block_capture_and_tail_is_drained(fake_asr):
    entered, release = threading.Event(), threading.Event()
    sent = []
    def send(data):
        entered.set()
        assert release.wait(2)
        sent.append(data)
        return True
    fake_asr.send_audio.side_effect = send
    transcriber = RealtimeTranscriber(save_audio=False)
    transcriber.start()
    data = feed(transcriber.recorder)
    assert entered.wait(2)
    feed(transcriber.recorder)
    feed(transcriber.recorder)
    assert transcriber.recorder.captured_bytes == 3 * len(data)
    release.set()
    transcriber.stop()
    assert len(sent) == 3
    assert transcriber.failed_audio_bytes == transcriber.unsent_audio_bytes == 0
    assert not transcriber._sender_thread.is_alive()


def test_send_failure_is_counted_and_recovery_is_reported(fake_asr):
    statuses = []
    second = threading.Event()
    def send(data):
        if not second.is_set():
            second.set()
            return False
        return True
    fake_asr.send_audio.side_effect = send
    transcriber = RealtimeTranscriber(save_audio=False)
    transcriber.start(on_status_change=statuses.append)
    feed(transcriber.recorder)
    assert second.wait(2)
    feed(transcriber.recorder)
    transcriber.stop()
    assert transcriber.failed_audio_bytes == 2048
    assert 'reconnecting' in statuses
    assert statuses.count('recording') == 2


def test_pause_duration_excludes_paused_time(fake_asr, monkeypatch):
    now = [100.0]
    monkeypatch.setattr('core.realtime_transcriber.time.monotonic', lambda: now[0])
    transcriber = RealtimeTranscriber(save_audio=False)
    transcriber.start()
    now[0] = 110
    transcriber.pause()
    now[0] = 130
    assert transcriber.get_duration() == 10
    transcriber.resume()
    now[0] = 135
    assert transcriber.get_duration() == 15
    transcriber.stop()


def test_asr_stop_retains_late_result_and_closes_resources():
    client = DashScopeASRClient(ASRConfig(api_key='test'))
    callback = client.callback = RealtimeASRCallback()
    callback.full_transcription = '第一句 '
    callback.current_partial = '临时'
    conversation = client.conversation = Mock()
    def finish(**kwargs):
        callback.full_transcription += '确认句'
        callback.current_partial = ''
    conversation.end_session.side_effect = finish
    client.is_running = True
    assert client.stop()
    assert client.get_transcription() == '第一句 确认句'
    assert client.callback is client.conversation is None
    conversation.close.assert_called_once()


def test_stop_cancels_reconnect_wait_immediately():
    client = DashScopeASRClient(ASRConfig(api_key='test', reconnect_delay=60))
    client.cancel_reconnect()
    started = time.monotonic()
    assert client._try_reconnect() is False
    assert time.monotonic() - started < 1


def test_cancel_interrupts_an_active_reconnect_wait():
    client = DashScopeASRClient(ASRConfig(api_key='test', reconnect_delay=60))
    worker = threading.Thread(target=client._try_reconnect)
    worker.start()
    deadline = time.monotonic() + 2
    while client._reconnect_count == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    client.cancel_reconnect()
    worker.join(timeout=1)
    assert not worker.is_alive()


def test_expired_drain_records_unsent_audio(fake_asr):
    transcriber = RealtimeTranscriber(save_audio=False)
    transcriber.recorder.audio_queue.put(b'\x00' * 2048)
    transcriber._drain_deadline = time.monotonic() - 1
    transcriber._stop_event.set()
    transcriber._send_audio_loop()
    assert transcriber.unsent_audio_bytes == 2048
    assert transcriber.recorder.audio_queue.empty()
    fake_asr.send_audio.assert_not_called()


def test_session_rotation_preserves_interrupted_partial(monkeypatch):
    client = DashScopeASRClient(ASRConfig(api_key='test'))
    client.callback = RealtimeASRCallback()
    client.callback.full_transcription = '完整句 '
    client.callback.current_partial = '被中断的句尾'
    old = client.conversation = Mock()
    replacement = Mock()
    monkeypatch.setattr('api.dashscope_asr.OmniRealtimeConversation', lambda **kwargs: replacement)
    on_final = Mock()
    assert client._create_new_session(on_final=on_final)
    on_final.assert_called_once_with('被中断的句尾')
    old.close.assert_called_once()
    assert client.get_transcription() == '完整句 被中断的句尾'
    client.stop()
