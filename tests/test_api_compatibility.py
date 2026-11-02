"""API endpoint and error-message compatibility tests."""

import os
import struct

import pytest
import requests
from websocket._abnf import ABNF

from api.bailian_llm import BailianLLMClient
from api.dashscope_asr import _describe_asr_close, _extract_transcript
from config.settings import (
    APISettings, _upsert_env_line, preview_asr_content, preview_llm_content,
    save_api_configuration, save_output_directory, settings,
)
from utils.exceptions import BailianAPIException
from utils.proxy import (
    apply_proxy_policy, bypass_proxy_for, is_loopback_proxy, parse_proxy_host_port,
    redact_proxy_url,
)


def test_public_endpoints_follow_region():
    # Arrange & Act
    api = APISettings(DASHSCOPE_REGION='ap-southeast-1', DASHSCOPE_WORKSPACE_ID='')

    # Assert
    assert api.http_base_url == 'https://dashscope-intl.aliyuncs.com/api/v1'
    assert api.ws_base_url == 'wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime'


def test_workspace_uses_dedicated_domain():
    # Arrange & Act
    api = APISettings(DASHSCOPE_REGION='cn-beijing', DASHSCOPE_WORKSPACE_ID='llm-test123')

    # Assert
    assert api.http_base_url == 'https://llm-test123.cn-beijing.maas.aliyuncs.com/api/v1'
    assert api.ws_base_url == 'wss://llm-test123.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime'


def test_explicit_endpoint_overrides_win():
    # Arrange & Act
    api = APISettings(
        DASHSCOPE_REGION='cn-beijing',
        DASHSCOPE_WORKSPACE_ID='llm-test123',
        DASHSCOPE_BASE_URL='https://example.com/api/v1',
        DASHSCOPE_WS_BASE_URL='wss://example.com/realtime',
    )

    # Assert
    assert api.http_base_url == 'https://example.com/api/v1'
    assert api.ws_base_url == 'wss://example.com/realtime'


def test_stash_is_used_for_partial_transcript():
    # Arrange & Act & Assert
    assert _extract_transcript({'text': '', 'stash': '你好'}) == '你好'
    assert _extract_transcript({'transcript': '你好世界'}) == '你好世界'


def test_quota_close_reason_is_actionable():
    # Arrange & Act
    message = _describe_asr_close(1007, 'The free tier of the model has been exhausted.')

    # Assert
    assert '免费额度' in message


def test_long_close_frame_is_accepted():
    # Arrange
    frame = ABNF(
        fin=1,
        opcode=ABNF.OPCODE_CLOSE,
        data=struct.pack('!H', 1007) + b'free tier exhausted. ' * 6,
    )

    # Act & Assert
    frame.validate()


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_quota_http_error_is_translated():
    # Arrange
    response = _FakeResponse(403, {'code': 'AllocationQuota.FreeTierOnly', 'message': 'Free quota exhausted.'})

    # Act & Assert
    with pytest.raises(BailianAPIException) as excinfo:
        BailianLLMClient._raise_for_http_error(response)
    assert excinfo.value.error_code == 'BAILIAN_QUOTA_EXCEEDED'
    assert '免费额度' in excinfo.value.message


def test_upsert_env_line_updates_and_appends():
    # Arrange
    lines = ['A=1', 'DASHSCOPE_REGION=old']

    # Act
    _upsert_env_line(lines, 'DASHSCOPE_REGION', 'cn-beijing')
    _upsert_env_line(lines, 'DASHSCOPE_WORKSPACE_ID', 'llm-test123')

    # Assert
    assert lines == [
        'A=1',
        'DASHSCOPE_REGION=cn-beijing',
        'DASHSCOPE_WORKSPACE_ID=llm-test123',
    ]


def test_proxy_url_parsing_and_loopback_detection():
    # Arrange & Act & Assert
    assert parse_proxy_host_port('http://127.0.0.1:7890') == ('127.0.0.1', 7890)
    assert parse_proxy_host_port('127.0.0.1:7890') == ('127.0.0.1', 7890)
    assert parse_proxy_host_port('') is None
    assert is_loopback_proxy('http://127.0.0.1:29290')
    assert is_loopback_proxy('http://localhost:7890')
    assert not is_loopback_proxy('http://10.0.0.1:3128')


def test_bypass_proxy_for_restores_environment(monkeypatch):
    # Arrange
    monkeypatch.setenv('NO_PROXY', 'example.com')
    # Windows 的环境变量名不区分大小写，删除 no_proxy 会连带删除 NO_PROXY。
    if os.name != 'nt':
        monkeypatch.delenv('no_proxy', raising=False)

    # Act
    with bypass_proxy_for(['dashscope.aliyuncs.com']):
        assert 'dashscope.aliyuncs.com' in os.environ['NO_PROXY']

    # Assert
    assert (os.environ.get('NO_PROXY') or os.environ.get('no_proxy')) == 'example.com'


def test_apply_direct_policy_adds_dashscope_hosts(monkeypatch):
    # Arrange
    monkeypatch.setenv('NO_PROXY', '')
    monkeypatch.setenv('no_proxy', '')

    # Act
    apply_proxy_policy('direct', '', ['dashscope.aliyuncs.com'])

    # Assert
    assert 'dashscope.aliyuncs.com' in os.environ['NO_PROXY']


def test_llm_retries_direct_on_loopback_proxy_error(monkeypatch):
    # Arrange
    client = BailianLLMClient(api_key='sk-test')
    calls = []

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {'output': {'choices': [{'message': {'content': 'OK'}}]}}

    def _fake_post(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise requests.exceptions.ProxyError('proxy down')
        return _FakeResponse()

    monkeypatch.setattr('api.bailian_llm.requests.post', _fake_post)
    monkeypatch.setattr('api.bailian_llm.should_fallback_to_direct', lambda *args, **kwargs: True)

    # Act
    result = client.generate('hi')

    # Assert
    assert result == 'OK'
    assert len(calls) == 2


def test_llm_request_keeps_zero_temperature_and_sends_seed(monkeypatch):
    # Arrange
    captured = {}

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {'output': {'choices': [{'message': {'content': 'OK'}}]}}

    def _fake_post(url, **kwargs):
        captured.update(kwargs['json'])
        return _FakeResponse()

    monkeypatch.setattr('api.bailian_llm.requests.post', _fake_post)
    client = BailianLLMClient(api_key='sk-test')

    # Act
    result = client.generate('hi', temperature=0.0, max_tokens=16)

    # Assert
    assert result == 'OK'
    assert captured['parameters']['temperature'] == 0.0
    assert captured['parameters']['seed'] == settings.api.bailian_seed
    assert captured['parameters']['max_tokens'] == 16


def test_llm_records_token_usage(monkeypatch):
    # Arrange
    client = BailianLLMClient(api_key='sk-test')

    class _FakeResponse:
        status_code = 200

        def json(self):
            return {
                'output': {'choices': [{'message': {'content': 'OK'}}]},
                'usage': {'total_tokens': 42},
            }

    monkeypatch.setattr('api.bailian_llm.requests.post', lambda *args, **kwargs: _FakeResponse())

    # Act
    result = client.generate('hi')

    # Assert
    assert result == 'OK'
    assert client.last_usage == {'total_tokens': 42}


def test_preview_llm_content_redacts_by_default(monkeypatch):
    # Arrange
    monkeypatch.setattr(settings.api, 'log_llm_raw', False)
    assert '<redacted' in preview_llm_content('敏感文本')

    # Act
    monkeypatch.setattr(settings.api, 'log_llm_raw', True)
    preview = preview_llm_content('敏感文本', 2)

    # Assert
    assert preview == '敏感'


def test_preview_asr_content_redacts_by_default(monkeypatch):
    # Arrange
    monkeypatch.setattr(settings.asr, 'log_asr_text', False)
    assert '<redacted' in preview_asr_content('录音内容')

    # Act
    monkeypatch.setattr(settings.asr, 'log_asr_text', True)
    preview = preview_asr_content('录音内容', 2)

    # Assert
    assert preview == '录音'


def test_upsert_env_line_rejects_newline_injection():
    # Arrange
    lines = ['A=1']

    # Act & Assert
    with pytest.raises(ValueError):
        _upsert_env_line(lines, 'DASHSCOPE_REGION', 'cn-beijing\nINJECTED=1')


def test_redact_proxy_url_hides_credentials():
    # Act & Assert
    assert redact_proxy_url('http://user:secret@127.0.0.1:7890') == 'http://***@127.0.0.1:7890'
    assert redact_proxy_url('http://127.0.0.1:7890') == 'http://127.0.0.1:7890'


def test_save_api_configuration_rejects_env_injection(tmp_path, monkeypatch):
    # Arrange
    monkeypatch.setattr('config.settings.project_root', tmp_path)
    env_file = tmp_path / '.env'
    env_file.write_text('DASHSCOPE_API_KEY=old\nOUTPUT_DIR=./output\n', encoding='utf-8')

    # Act
    saved = save_api_configuration('sk-valid\nINJECTED=1')

    # Assert
    assert saved is False
    assert env_file.read_text(encoding='utf-8') == 'DASHSCOPE_API_KEY=old\nOUTPUT_DIR=./output\n'


def test_save_output_directory_writes_valid_value(tmp_path, monkeypatch):
    # Arrange
    monkeypatch.setattr('config.settings.project_root', tmp_path)
    env_file = tmp_path / '.env'
    env_file.write_text('OUTPUT_DIR=./output\n', encoding='utf-8')

    # Act
    saved = save_output_directory('./exports')

    # Assert
    assert saved is True
    assert 'OUTPUT_DIR=./exports' in env_file.read_text(encoding='utf-8')
