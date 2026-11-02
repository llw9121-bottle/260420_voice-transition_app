"""本地 ASR provider 的配置、工厂与启动门禁测试。"""

from types import SimpleNamespace

from config.settings import (
    ASRSettings,
    check_api_configuration,
    get_local_asr_model_dir,
    normalize_asr_language,
    project_root,
    save_api_configuration,
    settings,
)


def _clear_provider_env(monkeypatch):
    monkeypatch.delenv('APP_FLAVOR', raising=False)
    monkeypatch.delenv('ASR_PROVIDER', raising=False)


def test_provider_defaults_to_cloud(monkeypatch):
    _clear_provider_env(monkeypatch)
    assert ASRSettings(_env_file=None).provider == 'cloud'


def test_provider_follows_local_flavor(monkeypatch):
    monkeypatch.setenv('APP_FLAVOR', 'local')
    monkeypatch.delenv('ASR_PROVIDER', raising=False)
    assert ASRSettings(_env_file=None).provider == 'local'


def test_explicit_provider_overrides_flavor(monkeypatch):
    monkeypatch.setenv('APP_FLAVOR', 'local')
    monkeypatch.setenv('ASR_PROVIDER', 'cloud')
    assert ASRSettings(_env_file=None).provider == 'cloud'


def test_threads_are_clamped(monkeypatch):
    monkeypatch.setenv('ASR_LOCAL_NUM_THREADS', '99')
    assert ASRSettings(_env_file=None).local_num_threads == 8
    monkeypatch.setenv('ASR_LOCAL_NUM_THREADS', '0')
    assert ASRSettings(_env_file=None).local_num_threads == 1


def test_model_dir_default(monkeypatch):
    monkeypatch.setattr(settings.asr, 'local_model_dir', '')
    assert get_local_asr_model_dir() == project_root / 'models' / 'asr'


def test_model_dir_relative(monkeypatch):
    monkeypatch.setattr(settings.asr, 'local_model_dir', 'custom/models')
    assert get_local_asr_model_dir() == project_root / 'custom' / 'models'


def test_model_dir_absolute(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.asr, 'local_model_dir', str(tmp_path))
    assert get_local_asr_model_dir() == tmp_path


def test_local_asr_needs_no_dashscope_key(monkeypatch):
    monkeypatch.setattr(settings.asr, 'provider', 'local')
    monkeypatch.setattr(settings.api, 'dashscope_api_key', '')

    result = check_api_configuration()

    assert result['asr_configured'] is True
    assert result['asr_provider'] == 'local'


def test_cloud_requires_dashscope_key(monkeypatch):
    monkeypatch.setattr(settings.asr, 'provider', 'cloud')
    monkeypatch.setattr(settings.api, 'dashscope_api_key', '')

    result = check_api_configuration()

    assert result['asr_configured'] is False


def test_normalize_language_in_local_mode(monkeypatch):
    monkeypatch.setattr(settings.asr, 'provider', 'local')
    assert normalize_asr_language('ja') == 'zh'
    assert normalize_asr_language('yue') == 'zh'
    assert normalize_asr_language('en') == 'en'
    assert normalize_asr_language('') == 'zh'


def test_normalize_language_in_cloud_mode(monkeypatch):
    monkeypatch.setattr(settings.asr, 'provider', 'cloud')
    assert normalize_asr_language('ja') == 'ja'


def test_save_allows_empty_dashscope_for_local(tmp_path, monkeypatch):
    monkeypatch.setattr('config.settings.project_root', tmp_path)

    assert save_api_configuration(
        '', 'sk-bailian-key', allow_empty_dashscope=True
    ) is True

    content = (tmp_path / '.env').read_text(encoding='utf-8')
    assert 'DASHSCOPE_API_KEY=' in content
    assert 'BAILIAN_API_KEY=sk-bailian-key' in content


def test_save_rejects_empty_dashscope_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr('config.settings.project_root', tmp_path)

    assert save_api_configuration('') is False
    assert not (tmp_path / '.env').exists()


def test_factory_cloud_uses_module_level_client(monkeypatch):
    from core import realtime_transcriber

    sentinel = object()
    monkeypatch.setattr(
        realtime_transcriber, 'DashScopeASRClient', lambda config: sentinel
    )
    monkeypatch.setattr(settings.asr, 'provider', 'cloud')

    assert realtime_transcriber._create_asr_client(object()) is sentinel


def test_factory_local_returns_local_client(monkeypatch):
    from api.local_asr import LocalASRClient
    from core import realtime_transcriber

    monkeypatch.setattr(settings.asr, 'provider', 'local')

    client = realtime_transcriber._create_asr_client(
        SimpleNamespace(sample_rate=16000, language='zh')
    )

    assert isinstance(client, LocalASRClient)
