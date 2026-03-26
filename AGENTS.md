# AGENTS.md

本文件为 Codex (Codex.ai/code) 在此代码仓库中工作时提供指导。

## 项目概述

NeoFish 是一个自主 AI Agent 系统，可以控制浏览器执行用户任务。用户通过自然语言交互，Agent 可以导航网站、点击元素、提取信息和管理文件。

**架构**：前后端分离，通过 WebSocket 实现实时通信。

- **后端**：Python (FastAPI + Playwright + Anthropic/OpenAI API)
- **前端**：Vue 3 + TypeScript + Vite + TailwindCSS

## 开发命令

### 后端 (Python)

```bash
# 启动后端服务
uv run uvicorn main:app --reload

# 安装 Python 依赖（uv 会自动处理）
uv sync
```

### 前端 (Vue)

```bash
cd frontend
npm install        # 安装依赖
npm run dev        # 启动开发服务器 (http://localhost:5173)
npm run build      # 构建生产版本
```

### Playwright（首次设置）

```bash
# 安装浏览器二进制文件
uv run playwright install chromium
```

## 核心架构概念

### 多平台适配器模式

所有消息平台都实现 `PlatformAdapter` (`platforms/base.py`)。Agent 核心 (`agent.py`) 通过这个统一接口与任何平台交互。

- `platforms/web.py` - 基于 WebSocket 的 Web UI
- `platforms/telegram.py` - Telegram 机器人集成
- `platforms/qq.py` - QQ 机器人（通过 NapCat/go-cqhttp）

添加新平台时，需实现 `start()`、`stop()`、`send_message()`、`request_action()` 和 `send_file()` 方法。

### 浏览器自动化 (PlaywrightManager)

`playwright_manager.py` 管理一个持久化的 Chromium 上下文，具有以下能力：

- **ARIA 快照**：`get_aria_snapshot()` 返回带有 `[ref=e1]` ID 的交互元素，实现可靠的元素选择
- **人工介入**：`block_for_human()` 暂停 Agent 执行，等待用户处理（验证码、登录等）
- **接管模式**：在无头模式（Agent）和有头模式（用户）之间切换浏览器控制权
- **状态持久化**：浏览器状态保存在 `browser_state/` 目录

### Agent 循环 (agent.py)

主循环遵循：**观察（截图）→ 思考（LLM）→ 行动（工具）**

关键特性：
- **上下文压缩**：双层系统（微压缩 + LLM 摘要），在 token 超过阈值时触发
- **任务管理**：持久化任务，可在上下文压缩后保留
- **后台任务**：非阻塞命令执行，支持结果回传

### 工具系统

Agent 可以使用以下工具类别：

1. **浏览器**：`snapshot`、`navigate`、`click`、`type_text`、`scroll`、`send_screenshot`、`request_human_assistance`
2. **文件**：`read_file`、`write_file`、`edit_file`、`send_file`、`run_bash`
3. **任务**：`task_create`、`task_get`、`task_update`、`task_list`
4. **后台**：`background_run`、`check_background`
5. **上下文**：`compact`（手动触发压缩）

### 消息流程

1. 用户发送消息 → 平台适配器接收
2. 适配器调用 `agent.py` 中的 `run_agent_loop()`
3. Agent 执行思考-行动循环，调用 `ws_send_msg` 回调
4. 平台适配器将响应发送回用户

## 环境配置

复制 `.env.example` 为 `.env` 并配置：

- `ANTHROPIC_API_KEY` - LLM 所需的 API 密钥
- `ANTHROPIC_BASE_URL` - API 端点（支持代理）
- `MODEL_NAME` - 使用的模型（默认：`Codex-3-7-sonnet-20250219`）
- `WORKDIR` - 文件操作的工作目录
- 平台特定令牌（Telegram、QQ）- 可选

## 重要文件

| 文件 | 用途 |
|------|------|
| `main.py` | FastAPI 应用、REST 端点、WebSocket 处理器 |
| `agent.py` | Agent 核心循环、工具定义、上下文压缩 |
| `playwright_manager.py` | 浏览器生命周期、ARIA 快照、接管模式 |
| `config.py` | 集中化环境配置 |
| `platforms/base.py` | 抽象适配器接口 |
| `workspace_manager.py` | 工作区沙箱内的文件操作 |
| `task_manager.py` | 持久化任务跟踪 |
| `background_manager.py` | 非阻塞命令执行 |