"""本地专用构建的启动钩子：固定 ASR 后端为 local。

在 config.settings 导入之前执行，因此 ASRSettings.provider 的默认值正确。
load_dotenv 默认不覆盖已有环境变量，所以 .env 无法把本地版切回 cloud。
"""

import os

os.environ['APP_FLAVOR'] = 'local'
os.environ.setdefault('ASR_PROVIDER', 'local')
