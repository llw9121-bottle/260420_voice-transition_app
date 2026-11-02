# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller 配置文件 - 本地 ASR 版
# 使用方法: pyinstaller app-local.spec
#
# 与 app.spec 的差异：
# - 打包 sherpa-onnx 及其原生运行时
# - 通过 runtime hook 固定 ASR_PROVIDER=local
# - 模型不进入 datas，而是与 exe 同级放在 models/asr/
# - 关闭 UPX，避免破坏 onnxruntime 原生 DLL

from PyInstaller.utils.hooks import collect_all

block_cipher = None

sherpa_datas, sherpa_binaries, sherpa_hiddenimports = collect_all('sherpa_onnx')
try:
    core_datas, core_binaries, core_hiddenimports = collect_all('sherpa_onnx_core')
except Exception:
    # sherpa-onnx-core 是数据型 distribution，部分环境无法按包名收集。
    core_datas, core_binaries, core_hiddenimports = [], [], []

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=sherpa_binaries + core_binaries,
    datas=[('.env.example', '.')] + sherpa_datas + core_datas,
    hiddenimports=[
        'pyaudio',
        'customtkinter',
        'loguru',
        'pydantic',
        'pydantic_settings',
        'dotenv',
        'requests',
        'dashscope',
        'docx',
        'numpy',
        'sherpa_onnx',
        'api.local_asr',
    ] + sherpa_hiddenimports + core_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        'packaging/runtime_hook_local_flavor.py',
        'packaging/runtime_hook_local_dlls.py',
    ],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='VoiceTranscriptionLocal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
