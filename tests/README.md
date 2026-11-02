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

仅运行离线单元测试（不采集麦克风，不调用真实 API）：

```bash
python -m pytest tests/ --ignore=tests/e2e -v -m "not requires_api"
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
| `test_session_store.py` | 原子保存、写入失败保护、完整会话恢复 | 否 | 否 |
| `test_recording_pipeline.py` | 有界缓冲、音频落盘、网络阻塞、停止收尾与重连取消 | 否 | 否（使用 mock） |
| `test_app_lifecycle.py` | 后台启停、保存顺序、暂停自动保存、退出失败保护与界面状态 | 否 | 否（无窗口） |
| `test_review.py` | 修订版本上限、原文映射、差异范围、空稿导出 | 否 | 否 |
| `test_audio_player.py` | 流式回放、定位、取消隔离、设备异常与资源释放 | 否 | 否（使用 mock） |
| `test_review_workspace.py` | 原生编辑、撤销、搜索、对照、窄屏布局与历史界面 | 否 | 否（需可用 Tk） |
| `test_export_workflow.py` | 后台导出、覆盖检查、原子替换失败、保留文件名与整理说明导出 | 否 | 否 |
| `test_processing.py` | 分块进度与取消、降级提示、响应校验、长文引文偏移 | 否 | 否（使用 mock） |
| `test_local_asr.py` | 本地流式客户端：模型校验、语言限制、partial/final 顺序、停止幂等与限时 | 否 | 否（使用 fake sherpa） |
| `test_local_config.py` | provider/flavor 解析、模型目录、启动门禁、可选 DashScope Key、客户端工厂 | 否 | 否 |

第二轮回归还覆盖草稿保存后切换会话、导出前收集编辑、重整版本保留、过期结果隔离、句级估计时间及旧快照兼容。

第三轮回归覆盖取消后丢弃远程结果、防止重复整理、慢磁盘合并自动保存、导出期间退出保护，以及原生导出窗口和阶段反馈。所有 AI 调用、录音和播放设备均使用替身；原生窗口测试只写测试目录。

完整离线检查使用 `pytest tests/ --ignore=tests/e2e -m "not requires_api"`，避免旧的未标记端到端脚本访问真实 API 或声卡。

原生窗口测试默认跳过。在安装完整 Tk 的 Python 环境中，使用 PowerShell 显式运行：

```powershell
$env:RUN_GUI_TESTS = '1'
pytest tests/test_review_workspace.py -v
```

原生测试会打开测试窗口，使用示例数据，不修改用户偏好、不刷新真实音频设备，也不调用网络服务。Tcl/Tk 的脚本和二进制版本必须匹配。

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
