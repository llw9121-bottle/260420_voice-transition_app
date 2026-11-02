# 打包说明 - 绿色可执行版

本项目可以使用 PyInstaller 打包为独立可执行文件，用户无需安装 Python 即可直接运行。

---

## Windows 绿色版打包

### 开发者打包步骤

#### 环境准备
```bash
# 1. 安装 PyInstaller
pip install pyinstaller

# 2. 确保所有依赖都已安装
pip install -r requirements.txt
```

#### 执行打包
```bash
pyinstaller app.spec
```

打包完成后，可执行文件和依赖在 `dist/` 目录。

#### 制作绿色压缩包
当前 `app.spec` 使用 one-file 模式，`dist/` 中只需分发主程序：

```text
dist/
└── VoiceTranscription.exe      # 单文件主程序，约 45MB
```

将 `VoiceTranscription.exe` 压缩为 `VoiceTranscription-Windows.zip`。**不要把本机 `dist/.env`、`sessions/`、`output/`、`logs/` 一起打包**，这些目录可能包含 API Key 或录音内容。

---

## Windows 本地 ASR 版打包

本地版与云端版共用同一份源码，但使用独立的 spec、依赖和发布资产。**云端 `app.spec` 保持不变。**

### 1. 安装依赖

```bash
pip install -r requirements-local.txt
pip install pyinstaller==6.22.3
```

### 2. 下载并校验模型

```bash
python scripts/fetch_local_model.py --dest model-cache/models/asr
```

默认从模型镜像逐个下载 `encoder.int8.onnx`、`decoder.int8.onnx`、`tokens.txt`（约 237MB），每个文件都按脚本内固定的 SHA256 校验，并生成 `MANIFEST.txt`。

如需从官方归档构建，可使用归档模式：

```bash
python scripts/fetch_local_model.py \
  --url https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-paraformer-bilingual-zh-en.tar.bz2 \
  --sha256 <ARCHIVE_SHA256> \
  --dest model-cache/models/asr \
  --cache-dir model-cache
```

### 3. 打包

```bash
pyinstaller app-local.spec --noconfirm --clean
```

产物：`dist/VoiceTranscriptionLocal.exe`（one-file）。

### 4. 组装 zip

```text
VoiceTranscription-Windows-Local.zip
├── VoiceTranscriptionLocal.exe
├── models/asr/{encoder.int8.onnx,decoder.int8.onnx,tokens.txt,MANIFEST.txt}
├── README-LOCAL.txt
├── THIRD_PARTY_NOTICES.txt
└── LOCAL_BUILD_INFO.txt
```

`models/` 必须与 exe 位于同一目录。模型**不能**放进 PyInstaller `datas`，否则 one-file 每次启动都会把数百 MB 解压到临时目录。

### 5. CI

`.github/workflows/build-local.yml` 仅手动触发（`workflow_dispatch`），默认 `upload=false` 只产出 artifact；确认无误后改为 `upload=true`，通过 `gh release upload --clobber` 追加到 v2.0 Release，不修改标题、正文和 tag。

### 6. 验收

- 完整解压后断网运行，无需任何 Key 即可转写；
- 运行 `VoiceTranscriptionLocal.exe --check-local-asr`，退出码应为 0；
- 把 `models` 改名后，启动提示应包含模型路径和修复方法；
- 未配置百炼 Key 时，AI 整理提示清晰，转写不受影响。

---

## 👤 Windows 用户端 - 绿色安装使用说明

### 系统要求
- Windows 10 / Windows 11（64位）
- 约 200MB 磁盘空间

### 安装步骤
1. **下载压缩包** `VoiceTranscription-Windows.zip` 到电脑
2. **解压缩**到任意文件夹（建议路径不要有中文）
3. **双击运行** `VoiceTranscription.exe`
4. **首次启动**会自动弹出 API Key 配置对话框，输入你的阿里云 DashScope API Key 即可使用

### 获取 API Key
1. 访问 [阿里云 DashScope 控制台](https://dashscope.aliyun.com/)
2. 登录或注册阿里云账号
3. 开通 DashScope 服务
4. 在"API Keys"页面创建并复制你的 API Key
5. 将复制的 API Key 粘贴到应用配置对话框中点击保存
6. 重启应用即可开始使用

### 注意事项
- **首次使用必须配置 API Key**，否则无法使用语音识别功能
- API Key 保存在程序所在目录的 `.env` 文件中
- 如果需要修改 API Key，可以在主界面右侧设置面板点击「🔑 设置 API Key」
- 输出的文档默认保存在程序目录 `output/` 文件夹下

### 常见问题

**Q: 双击后没反应/无法启动怎么办？**

A: 请确保你解压缩完整，压缩包内所有文件都要一起解压出来。**不要直接在压缩包内双击运行**，必须先解压到文件夹再运行。

**Q: Windows 提示"已保护你的电脑"怎么办？**

A: 这是 Windows SmartScreen 拦截，这是对未签名应用的正常提示。可以点击「更多信息」→「仍运行」即可启动。

**Q: 杀毒软件提示病毒怎么办？**

A: PyInstaller 打包的独立 exe 可能会被部分杀毒软件误报，你可以添加信任。本项目完全开源，不含恶意代码。

---

## macOS 绿色版打包

### 开发者打包步骤

#### 环境准备
```bash
# 1. 安装依赖（需要先安装 Homebrew）
brew install portaudio
pip install pyaudio

# 2. 安装 PyInstaller 和项目依赖
pip install pyinstaller
pip install -r requirements.txt
```

#### 执行打包
```bash
pyinstaller app-mac.spec
```

打包完成后在 `dist/` 目录生成 `VoiceTranscription.app`。

#### 制作绿色压缩包
```bash
cd dist
zip -r VoiceTranscription-macOS.zip VoiceTranscription.app
```

得到 `VoiceTranscription-macOS.zip`，这就是绿色安装包。

#### 可选：代码签名（需要 Apple Developer 账号 $99/年）
如果你有 Apple Developer 会员，可以签名后用户可以直接双击打开：
```bash
codesign --force --deep --sign "Apple Development: Your Name (XXXXXX)" dist/VoiceTranscription.app
```

---

## 👤 macOS 用户端 - 绿色安装使用说明

### 系统要求
- macOS 12.0 或更高版本
- 构建产物与构建机架构一致（Intel 或 Apple Silicon）；如架构不匹配，请在对应 Mac 上重新构建
- 约 250MB 磁盘空间

### 安装步骤

#### 方式一：解压即用（推荐，无签名绿色版）
1. **下载压缩包** `VoiceTranscription-macOS.zip` 到电脑
2. **双击解压**得到 `VoiceTranscription.app`
3. 建议将应用放到用户目录下的独立文件夹（如 `~/Applications/VoiceTranscription`）；程序会在 `.app` 同级生成 `.env`、`sessions`、`output`、`logs`
4. **首次打开**：必须**右键点击图标** → 选择「打开」
   > ⚠️  因为是未签名应用，**不能直接双击打开**，否则 macOS 会提示"无法打开"。这是 macOS 安全机制，第一次右键打开后，以后就可以正常双击打开了。
5. 首次启动会自动弹出 API Key 配置对话框，输入你的阿里云 DashScope API Key 即可使用

#### 方式二：已签名版本（如果开发者提供了签名）
1. 下载解压后直接双击就能打开，和正规 App 体验一样

### 获取 API Key
1. 访问 [阿里云 DashScope 控制台](https://dashscope.aliyun.com/)
2. 登录或注册阿里云账号
3. 开通 DashScope 服务
4. 在"API Keys"页面创建并复制你的 API Key
5. 将复制的 API Key 粘贴到应用配置对话框中点击保存
6. 重启应用即可开始使用

### 麦克风权限
首次使用录音时，macOS 会请求麦克风权限，请在**系统设置 → 隐私与安全性 → 麦克风**中允许 VoiceTranscription 访问。

### 注意事项
- **首次使用必须配置 API Key**，否则无法使用语音识别功能
- API Key 保存在应用所在目录的 `.env` 文件中
- 如果需要修改 API Key，可以在主界面右侧设置面板点击「🔑 设置 API Key」
- 输出的文档默认保存在应用所在目录 `output/` 文件夹下

### 常见问题

**Q: 提示"无法打开"、"开发者无法验证"怎么办？**

A: 这是正常的，因为应用没有苹果签名。解决方法：
- **右键点击应用图标** → 选择「打开」
- 在弹出的对话框中点击「打开」即可
- 完成一次后，以后就可以直接双击打开了

或者，你也可以在：
**系统设置 → 隐私与安全性** → 往下滑找到「仍要打开」按钮点击。

**Q: 启动后立即崩溃，提示 `dyld: Library not loaded` 怎么办？**

A: 这是因为你的电脑缺少 `portaudio` 依赖库（PyAudio 需要它）。打开终端执行：
```bash
brew install portaudio
```
> 如果没有安装 brew，先安装 Homebrew：https://brew.sh/

安装完 portaudio 后重新打开应用即可。

**Q: Apple Silicon (M1/M2/M3) 能运行吗？**

A: 可以。在 Apple Silicon 机器上打包会生成原生 arm64 版本；在 Intel Mac 上打包会生成 x86_64 版本。`universal2` 需要 PyAudio、portaudio 及其他二进制同时提供 universal 架构，不能仅靠 `--target-arch universal2` 保证成功。CI 默认使用 `macos-latest` 的构建机架构，如需覆盖两类 Mac，请分别在对应架构上构建。

---

## 打包开发者笔记

### PyInstaller 参数说明

- `console=False`: 不显示终端窗口，只显示GUI
- `upx=True`: 使用 UPX 压缩减小体积（需要提前安装 UPX）
- `upx=False`: 本地 ASR 版关闭 UPX，避免破坏 onnxruntime / sherpa-onnx 原生 DLL
- `hiddenimports`: 列出 PyInstaller 可能找不到的依赖
- `runtime_hooks`: 本地版用于固定 `ASR_PROVIDER=local` 并补充 DLL 搜索路径
- macOS: 使用 `BUNDLE` 生成标准 .app 应用包

### 体积参考

| 平台 | 打包后大小（单文件） | 说明 |
|------|---------------------|------|
| Windows（云端版） | 约 45 MB | 当前 `app.spec` one-file 构建，UPX 压缩后 |
| Windows（本地 ASR 版） | 约 75 MB + 约 230 MB 模型 | `app-local.spec`；模型与 exe 同级，不进临时目录 |
| macOS | 约 50-80 MB | 视运行器架构和依赖版本而定 |

### 测试打包结果

打包完成后一定要在干净的环境测试一下：
1. 复制到一个没有安装 Python 的电脑（或虚拟机）
2. 解压后按照用户使用说明启动
3. 测试完整流程：配置 API Key → 录音 → 识别 → 导出
