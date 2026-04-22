# 语音实时转录系统 (Voice Transcription App)

基于阿里云 DashScope 实时语音识别的桌面应用程序，支持自定义行为匹配分析。

## 📋 功能特性

- **实时流式识别**：边录音边识别，结果即时显示
- **多种格式化风格**：
  - `raw` - 原始转录，不做处理
  - `cleaned` - 基础文本清洗，去除语气词和重复
  - `paragraphs` - 整理为自然段落
  - `behavior_match` - 关键行为匹配（使用百炼大模型分析）
- **自定义行为匹配**：用户可以定义自己感兴趣的行为模式，LLM 自动识别并标注
- **多种导出格式**：支持 Markdown、JSON、Word 文档导出
- **网络自动重连**：网络临时断开后自动恢复，不丢失已转录内容
- **内存优化**：长时间录音内存使用稳定

## 🖥 技术栈

- Python 3.10+
- PyAudio - 音频采集
- 阿里云 DashScope - 实时语音识别 (ASR)
- 阿里云百炼 - 大语言模型行为分析
- CustomTkinter - 现代化 GUI 界面
- python-docx - Word 文档导出
- loguru - 日志管理
- pydantic-settings - 配置管理

## 📦 安装

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd voice-transition-app
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

> **注意**: Windows 下安装 PyAudio 如果遇到问题，可以使用 pipwin:
> ```bash
> pip install pipwin
> pipwin install pyaudio
> ```

### 3. 配置 API Key

复制 `.env.example` 为 `.env`，填入你的阿里云 API Key：

```bash
cp .env.example .env
```

编辑 `.env`:

```env
DASHSCOPE_API_KEY=your_dashscope_api_key_here
BAILIAN_API_KEY=your_bailian_api_key_here  # 可选，默认使用 DASHSCOPE_API_KEY
DASHSCOPE_REGION=cn-beijing
OUTPUT_DIR=./output
```

> 需要阿里云账号并开通 DashScope 服务。获取 API Key: [https://help.aliyun.com/zh/dashscope/developer-reference/acquisition-and-configuration-of-api-key](https://help.aliyun.com/zh/dashscope/developer-reference/acquisition-and-configuration-of-api-key)

## 🚀 快速开始

运行应用：

```bash
python app.py
```

或：

```bash
python run_gui.py
```

## 📖 使用说明

### 基本流程

1. **选择格式化风格**：在界面上方下拉框选择转录风格
2. **开始录音**：点击「开始录音」按钮，允许应用访问麦克风
3. **实时查看结果**：转录结果会实时显示在主界面
4. **停止录音**：点击「停止录音」结束转录
5. **导出文档**：点击「导出」按钮，选择导出格式保存文件

### 行为匹配功能

1. 选择 `behavior_match` 风格
2. 点击「行为配置」打开配置对话框
3. 添加你想要识别的行为名称和描述
4. 保存配置后开始录音
5. 导出时 LLM 会自动识别文本中的匹配行为并标注

示例配置：
| 行为名称 | 行为描述 |
|---------|---------|
| 用户提出需求 | 用户提出了新的功能需求或需求变更 |
| 用户反馈问题 | 用户反馈使用中遇到的问题或bug |
| 确认需求 | 双方确认需求范围和验收标准 |

## 📁 项目结构

```
voice-transition-app/
├── api/                    # API 客户端层
│   ├── dashscope_asr.py   # DashScope 实时 ASR 客户端
│   └── bailian_llm.py     # 百炼大语言模型客户端
├── core/                   # 核心业务逻辑层
│   ├── audio_recorder.py  # PyAudio 音频采集
│   ├── realtime_transcriber.py  # 整合录音 + ASR
│   └── formatter/         # 文本格式化和导出
│       ├── base.py        # 基础数据结构
│       ├── styles.py      # 格式化风格实现
│       ├── behavior_matcher.py  # 行为匹配器
│       ├── exporters.py   # 导出器 (JSON/Markdown/Word)
│       └── naming.py      # 文件命名策略
├── gui/                    # GUI 界面层
│   ├── main_window.py     # 主窗口
│   ├── behavior_config_dialog.py  # 行为配置对话框
│   ├── export_dialog.py   # 导出对话框
│   └── ...
├── config/                 # 配置层
│   └── settings.py        # 应用配置管理
├── utils/                  # 工具模块
│   ├── exceptions.py      # 自定义异常
│   └── logger.py          # 日志配置
├── tests/                  # 测试
│   ├── test_config.py     # 配置单元测试
│   ├── test_formatter.py  # 格式化单元测试
│   └── e2e/               # 端到端功能测试
├── app.py                  # 应用入口
├── CLAUDE.md               # Claude Code 开发指南
├── requirements.txt        # Python 依赖
└── .gitignore              # Git 忽略规则
```

## 🧪 测试

```bash
# 运行单元测试（无需 API Key，离线运行）
pytest tests/ -v -m "not requires_api"

# 运行所有测试（包括需要 API Key 的端到端测试）
pytest tests/ -v
```

## 📝 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 🔗 相关链接

- [DashScope 官网](https://help.aliyun.com/zh/dashscope/)
- [CustomTkinter 文档](https://customtkinter.tomschimansky.com/)
