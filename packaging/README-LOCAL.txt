语音实时转录系统 · 本地识别版（v2.0）
========================================

这是一个基于本地语音识别引擎的 Windows 版本。
音频只在本机处理，不会上传到阿里云或其他服务器。

使用方法
--------
1. 将整个压缩包解压到一个独立文件夹（路径尽量不要包含中文）。
2. 不要单独移动 VoiceTranscriptionLocal.exe。
   models 文件夹必须与 exe 位于同一目录。
3. 双击 VoiceTranscriptionLocal.exe 启动。
4. 点击“开始录音”即可转写，无需填写 DashScope API Key。

目录结构
--------
VoiceTranscriptionLocal.exe
models\asr\model.int8.onnx
models\asr\tokens.txt
models\asr\silero_vad.onnx
README-LOCAL.txt
THIRD_PARTY_NOTICES.txt
LOCAL_BUILD_INFO.txt

已知限制
--------
- 支持中文、粤语、英文、日语、韩语；其他语言会回退到中文。
- 转写结果自带标点。
- 首次启动加载模型需要几秒钟；建议 4GB 以上内存。
- 模型约 240MB，请预留至少 1GB 磁盘空间。
- 识别按语音停顿出句，最终结果通常在停顿后 0.5–1 秒出现。

AI 整理功能
-----------
“段落整理（AI 语义分段）”和“行为分析”仍使用阿里云百炼大模型，
需要配置 Bailian API Key。转写文本会发送给百炼，但原始音频不会。

没有配置 Key 时：
- 本地转写、原始转录、清理口语、按停顿分段都可以正常使用；
- AI 功能会给出提示，不会影响已转录的文稿。

隐私说明
--------
- 本地识别版：音频不离开本机。
- AI 整理：转写文本会发送给阿里云百炼，具体边界见项目 README 的
  “数据隐私与高私密场景”章节。
- 如需完全离线，请不要使用 AI 整理功能。

故障排查
--------
如果提示“本地 ASR 模型缺失”，请确认：
1. 是从压缩包完整解压，而不是只复制了 exe；
2. models\asr 与 exe 在同一目录；
3. 三个模型文件都存在。

如果提示“内存不足”，请关闭其他程序后重试。

可以在命令行运行自检，确认模型与运行库是否正常：

    VoiceTranscriptionLocal.exe --check-local-asr

退出码为 0 表示模型和原生运行库加载成功。

版本
----
v2.0（本地识别版为同一版本的增量资产，版本号不变）
