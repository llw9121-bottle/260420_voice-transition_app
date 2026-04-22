"""
启动 GUI 应用程序

运行方式:
    python run_gui.py
"""

import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from app import VoiceTranscriptionApp
    
    if __name__ == "__main__":
        app = VoiceTranscriptionApp()
        app.run()
        
except ImportError as e:
    print(f"错误: 缺少必要的依赖 - {e}")
    print("\n请确保已安装以下依赖:")
    print("  - customtkinter")
    print("  - loguru")
    print("  - pydantic")
    print("  - python-dotenv")
    print("  - requests")
    print("\n安装命令:")
    print("  pip install customtkinter loguru pydantic pydantic-settings python-dotenv requests")
    
    input("\n按 Enter 键退出...")
    sys.exit(1)
    
except Exception as e:
    print(f"应用程序错误: {e}")
    import traceback
    traceback.print_exc()
    input("\n按 Enter 键退出...")
    sys.exit(1)
