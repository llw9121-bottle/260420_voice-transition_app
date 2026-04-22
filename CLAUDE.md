# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Table of Contents
- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Common Commands](#common-commands)
- [Development Guide](#development-guide)

## Project Overview

语音实时转录系统 - 是一个基于阿里云 DashScope 实时语音识别的桌面应用程序。

**核心功能:**
- 实时语音实时录音和流式识别
- 多种文本格式化风格（原始、清洗、分段、关键行为匹配
- 支持自定义行为匹配，使用百炼大模型分析对话内容
- 导出为 Markdown、JSON、Word 格式
- 图形界面使用 CustomTkinter

**技术栈:**
- Python 3.10+
- PyAudio - 音频录制
- DashScope - 实时语音识别 (ASR)
- 阿里云百炼 - 大语言模型行为匹配
- CustomTkinter - GUI 框架
- python-docx - Word 文档导出

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       GUI 层 (customtkinter)                 │
│  app.py / run_gui.py  ←  MainWindow, ExportDialog        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     Core 业务逻辑层                          │
│  realtime_transcriber  ← 整合录音 + ASR                  │
│  audio_recorder        ← PyAudio 音频采集                  │
│  formatter/            ← 文本格式化、行为匹配、导出        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      API 客户端层                            │
│  dashscope_asr.py    ← DashScope 实时 ASR (WebSocket)     │
│  bailian_llm.py      ← 百炼大语言模型 API 调用            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   配置和工具层                              │
│  config/settings.py  ← Pydantic Settings 配置管理         │
│  utils/             ← 异常处理、日志工具                    │
└─────────────────────────────────────────────────────────────┘
```

### 关键模块说明:

**config/settings.py**
- 使用 pydantic-settings 管理配置
- 从 `.env` 文件加载 API Key
- 提供 `check_api_configuration()` 检查配置状态

**api/dashscope_asr.py**
- 封装 DashScope OmniRealtimeConversation WebSocket 连接
- `DashScopeASRClient` - ASR 客户端，处理连接、发送音频、接收结果
- `RealtimeASRCallback` - 处理服务端事件（部分结果、最终结果、VAD事件）

**core/realtime_transcriber.py**
- `RealtimeTranscriber` - 整合音频录制 + ASR 识别
- 提供简洁的 API 供上层调用
- 支持回调: 中间结果、最终结果、状态变化

**core/formatter/**
- `base.py` - 定义基础数据结构 (`FormattedDocument`, `BehaviorMatch`, `TranscriptionSegment`) 和 `FormatterService`
- `styles.py` - 各种格式化风格实现
  - `CleanedStyle` - 基础清洗
  - `ParagraphStyle` - 分段整理
  - `BehaviorMatchStyle` - 关键行为匹配（调用 LLM）
- `behavior_matcher.py` - 行为匹配器，使用百炼 LLM 分析文本
- `exporters.py` - 导出器 (JSON/Markdown/Word)
- `naming.py` - 文件命名策略

**gui/**
- `main_window.py` - 主窗口，控制栏 + 转录区 + 设置面板 + 状态栏
- `export_dialog.py` - 导出对话框，选择格式和命名
- `behavior_config_dialog.py` - 行为配置对话框
- 所有 GUI 使用 CustomTkinter 组件

## Common Commands

### 环境安装
```bash
pip install -r requirements.txt
```

### 配置检查
```bash
python -c "from config.settings import settings, check_api_configuration; import json; print(json.dumps(check_api_configuration(), indent=2, ensure_ascii=False))"
```

### 运行应用
```bash
# 完整 GUI 应用
python app.py
# 或
python run_gui.py
```

### 运行测试
```bash
# 音频设备测试
python core/audio_recorder.py

# 实时转录功能测试（需要 API Key）
python test_realtime_asr.py

# 导出功能测试（无需 GUI）
python test_export_simple.py

# 完整导出测试
python test_export.py

# 行为匹配测试（需要 API Key）
python test_behavior_matcher_llm.py

# 格式化功能测试
python test_phase4_formatter.py

# 录音功能测试
python test_recording.py
```

## Development Guide

### 环境变量配置

在 `.env` 文件中配置:
```
DASHSCOPE_API_KEY=your_dashscope_api_key_here
BAILIAN_API_KEY=your_bailian_api_key_here  # 可选，默认使用 DASHSCOPE_API_KEY
DASHSCOPE_REGION=cn-beijing
OUTPUT_DIR=./output
```

### 格式化风格

应用支持四种格式化风格:
1. **raw** - 原始转录，不做任何处理
2. **cleaned** - 基础文本清洗，去掉语气词和重复
3. **paragraphs** - 整理为自然段落
4. **behavior_match** - 关键行为匹配，使用 LLM 识别用户定义的行为模式

### 添加新的格式化风格需要:
1. 在 `core/formatter/base.py` 的 `FormattingStyle` 添加枚举
2. 创建新的格式化类实现 `StyleFormatter` 协议
3. 在 `core/formatter/styles.py` 注册
4. 在 `gui/main_window.py` 的下拉框添加选项

### 导出格式

支持三种导出格式:
- JSON - 完整元数据 + 所有片段信息
- Markdown - 适合阅读和分享，包含行为匹配结果
- Word - 正式文档格式

### 代码约定

- 交互中文，代码英文，注释中文
- 缩进 4 空格
- 引号：单引号优先
- 使用 `loguru` 日志记录，不要使用 print 调试
- 配置通过 `config.settings.settings` 获取
- 异常定义在 `utils.exceptions`

### 输出目录

- 应用输出: `./output/`
- 日志文件: `./logs/`
- 测试输出: `./test_output/`

### 测试

项目采用双层测试结构：

```
tests/
├── __init__.py
├── conftest.py              # pytest 配置
├── test_config.py           # 配置模块单元测试
├── test_audio_device.py     # 音频设备检测单元测试
├── test_formatter.py        # 格式化模块单元测试
└── e2e/                     # 端到端功能测试
    ├── test_realtime_asr.py       # 实时转录测试（需要 API Key）
    ├── test_behavior_matcher_llm.py  # 行为匹配测试（需要 API Key）
    ├── test_export.py             # 完整导出测试
    └── ...
```

**运行测试：**
```bash
# 运行所有单元测试（无需 API Key，可离线运行）
pytest tests/ -v -m "not requires_api"

# 运行所有测试（包括需要 API Key 的端到端测试）
pytest tests/ -v

# 运行单个测试文件
pytest tests/test_config.py -v
```

**测试原则：**
- 单元测试：不依赖外部服务和 API Key，可离线运行
- 端到端测试：验证完整功能流程，需要有效 API Key
- 遵循 3A 结构：Arrange、Act、Assert
- 依赖必须隔离，禁止单元测试触碰真实 API
