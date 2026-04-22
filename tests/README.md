# 单元测试说明

本目录包含项目的结构化单元测试。

## 运行测试

### 安装 pytest

```bash
pip install pytest
```

### 运行所有测试

```bash
pytest tests/ -v
```

### 运行单个测试文件

```bash
pytest tests/test_config.py -v
pytest tests/test_audio_device.py -v
pytest tests/test_formatter.py -v
```

### 运行时显示标准输出

```bash
pytest tests/ -v -s
```

## 测试分类

| 文件 | 说明 | 是否需要网络 | 是否需要硬件 |
|------|------|-------------|--------------|
| `test_config.py` | 配置模块加载和验证 | 否 | 否 |
| `test_audio_device.py` | 音频设备信息解析和配置 | 否 | 否（使用mock） |
| `test_formatter.py` | 文本格式化和命名策略 | 否 | 否 |

## 添加新测试

请遵循以下约定：

1. 文件名以 `test_` 开头
2. 测试类以 `Test` 开头
3. 测试方法以 `test_` 开头
4. 不需要 API Key 或实际硬件就能离线运行
5. 使用 mock 模拟外部依赖

## 现有功能性测试

项目根目录下还有一些端到端功能性测试：

- `test_recording.py` - 音频录制完整测试
- `test_realtime_asr.py` - 实时语音识别测试（需要 API Key）
- `test_phase4_formatter.py` - 格式化模块完整测试
- `test_behavior_matcher_llm.py` - 行为匹配 LLM 测试（需要 API Key）
