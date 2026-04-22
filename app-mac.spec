# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller 配置文件 - 语音实时转录系统
# macOS 绿色版打包 (.app)
# 使用方法: pyinstaller app-mac.spec

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('.env.example', '.'),
    ],
    hiddenimports=[
        'pyaudio',
        'customtkinter',
        'PIL',
        'loguru',
        'pydantic',
        'pydantic_settings',
        'python-dotenv',
        'openai',
        'dashscope',
        'docx',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='VoiceTranscription',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    name='VoiceTranscription.app',
    icon=None,  # 可在此处添加 .icns 图标文件路径
    bundle_id='com.yourname.VoiceTranscription',
    info_plist={
        'NSMicrophoneUsageDescription': '需要麦克风权限进行语音录音',
        'CFBundleShortVersionString': '1.1.0',
        'CFBundleVersion': '1.1.0',
    },
)
