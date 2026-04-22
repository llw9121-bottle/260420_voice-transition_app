# 打包说明 - 绿色可执行版

本项目可以使用 PyInstaller 打包为独立可执行文件，用户无需安装 Python 即可直接运行。

## Windows 绿色版打包

### 环境准备

```bash
# 1. 安装 PyInstaller
pip install pyinstaller

# 2. 确保所有依赖都已安装
pip install -r requirements.txt
```

### 执行打包

```bash
pyinstaller app.spec
```

打包完成后，可执行文件在 `dist/VoiceTranscription.exe`。

### 制作绿色压缩包

打包完成后，将以下文件/文件夹一起压缩：
```
dist/
├── VoiceTranscription.exe      # 主程序
├── 所有 PyInstaller 生成的 .dll 和支持文件
```

将整个 `dist` 文件夹压缩为 `VoiceTranscription.zip`，这就是绿色安装包。

---

## 👤 用户端 - 绿色安装使用说明

### 系统要求

- Windows 10 / Windows 11（64位）
- 约 200MB 磁盘空间

### 安装步骤

1. **下载压缩包** `VoiceTranscription.zip` 到电脑
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

A: 请确保你解压缩完整，压缩包内所有文件都要一起解压出来。不要直接在压缩包内双击运行。

**Q: Windows 提示"已保护你的电脑"怎么办？**

A: 这是 Windows SmartScreen 拦截，可以点击「更多信息」→「仍运行」即可启动。这是因为应用没有数字签名，属于正常情况。

**Q: 杀毒软件提示病毒怎么办？**

A: PyInstaller 打包的独立 exe 可能会被部分杀毒软件误报，你可以添加信任。本项目完全开源，不含恶意代码。

---

## macOS 绿色版打包（可选）

### 打包命令

```bash
pyinstaller app-mac.spec
```

打包完成后在 `dist/` 目录生成 `VoiceTranscription.app`。

### 用户端使用说明

1. 下载 `VoiceTranscription.zip` 压缩包
2. 解压到「应用程序」文件夹
3. **首次打开**需要右键点击图标 → 选择「打开」（因为未签名，不能直接双击）
4. 之后就可以正常打开使用了
5. 如果遇到 `dyld: Library not loaded` 错误，请先安装 portaudio：
   ```bash
   brew install portaudio
   ```

### 代码签名（可选）

如果你有 Apple Developer 账号（$99/年），可以对 App 签名，这样用户就能直接双击打开：

```bash
codesign --force --deep --sign "Apple Development: Your Name (XXXXXX)" dist/VoiceTranscription.app
```

---

## 打包开发者笔记

### PyInstaller 参数说明

- `console=False`: 不显示黑框控制台窗口，只显示GUI
- `upx=True`: 使用 UPX 压缩减小体积（需要提前安装 UPX）
- `hiddenimports`: 列出 PyInstaller 可能找不到的依赖

### 体积优化

- 打包后大约 80-150 MB（取决于 Python 版本）
- 使用 UPX 可以压缩到 50-80 MB 左右
- 如果需要更小体积，可以考虑使用 `--onefile` 单文件模式，但启动会更慢

### 测试打包结果

打包完成后一定要在干净的环境测试一下：
1. 复制到一个没有 Python 的 Windows 电脑（或虚拟机）
2. 解压后双击运行
3. 测试完整流程：配置 API Key → 录音 → 识别 → 导出
