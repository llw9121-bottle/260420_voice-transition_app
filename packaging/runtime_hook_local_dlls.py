"""为 one-file 包中的原生 DLL 补充搜索路径。

sherpa-onnx 与 onnxruntime 的 DLL 位于 PyInstaller 的临时解压目录，
Windows 需要显式注册目录才能被延迟加载。
"""

import os
import sys

if getattr(sys, 'frozen', False):
    base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    for relative in (
        '',
        'sherpa_onnx',
        os.path.join('sherpa_onnx', 'lib'),
        os.path.join('onnxruntime', 'capi'),
    ):
        path = os.path.join(base, relative)
        if os.path.isdir(path) and hasattr(os, 'add_dll_directory'):
            try:
                os.add_dll_directory(path)
            except OSError:
                pass
