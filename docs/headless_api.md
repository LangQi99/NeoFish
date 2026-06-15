# NeoFish Headless API

一个面向"程序对程序"集成的纯 HTTP 接口——**不需要启动前端**，默认直接拉起本机有头 Chrome 窗口运行 Agent。

适合的场景：把 NeoFish 作为后端能力塞到别的应用里（Slack Bot、脚本、内部工单系统、企业微信机器人、另一套 Web 前端……）。调用方只关心"发一句话 → 拿结果"，其它交给 NeoFish。

---

## 启动

```bash
uv run python run_headless.py
# 或者：
uv run uvicorn run_headless:app --host 0.0.0.0 --port 8100
```

首次运行若浏览器内核未装：`uv run playwright install chromium`。

### 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `HEADLESS_API_HOST` | `0.0.0.0` | 监听地址 |
| `HEADLESS_API_PORT` | `8100` | 监听端口 |
| `NEOFISH_HEADLESS_BROWSER_MODE` | `local_chrome` | `local_chrome` 用本机 Chrome 弹出可见窗口；`headless` 切回无头 |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` / `MODEL_NAME` | 同主服务 | LLM 配置 |

和 `main.py`（带前端的服务）**共用 `browser_state` 目录**，即和 Web UI 登录过的 Cookie 互通。两个服务不建议同时跑（会抢同一份 profile）。

---

## 交互模型

### 基本流程

1. 调用方 `POST /v1/chat` 发一句话。
2. 服务器同步等待，直到 Agent 走到一个**终止状态**（两种），才返回 HTTP 响应：
   - **completed** — 任务跑完了，附带最终报告
   - **needs_input** — Agent 卡住了（登录墙、验证码、需要用户确认/补充上下文），等待人类接管或追加指令
3. 同一个 `session_id` 可以被反复 POST，行为是：
   - 如果 Agent 已完成（idle），新消息视为"继续任务 / 新子任务"，复用浏览器上下文 + session memory
   - 如果 Agent 还阻塞在 `needs_input`，新消息会被入队并自动唤醒 Agent（作为追加上下文继续执行）

### 流式模式

如果调用方希望实时接收 Agent 的中间状态，可以改用 `POST /v1/chat/stream`。它使用 Server-Sent Events (SSE) 返回事件流：

- 首个事件为 `{"type":"start","session_id":"..."}`。
- 执行过程中会持续收到 `info`、`needs_input`、`error` 等事件。
- 服务端 120 秒内没有新事件时会发送 `{"type":"heartbeat"}` 保持连接。
- 任务结束时发送 `{"type":"done"}`，客户端收到后即可关闭连接。

流式接口适合机器人、后台任务面板、命令行工具等需要展示执行进度的集成场景。它每次调用都会启动一次新的 Agent 运行；如果同一个 `session_id` 已有任务在跑，会返回 `409 Session already busy`。

### 人工接管

`needs_input` 通常对应登录、扫码、验证码、或者 Agent 主动呼叫人工。因为默认用的是**有头 Chrome 窗口**，调用方把 `needs_input` 返回给用户后，用户可以直接在弹出的 Chrome 窗口里手动操作；操作完后再 `POST /v1/chat`，消息内容比如 `"已经登录好了，继续"`，Agent 就会恢复执行。

---

## Endpoints

### `POST /v1/chat`

**请求 body**（`application/json`）：

```jsonc
{
  "message": "打开掘金搜索 vue3 并把前三篇文章标题发给我",
  "session_id": "可选；第一次调用不填，服务器会生成并回传",
  "images": ["data:image/png;base64,...", "..."],   // 可选，要喂给 Agent 的图片
  "timeout_seconds": 120                              // 可选，本次 HTTP 调用最多等多久
}
```

**响应（两态）**：

```jsonc
// 任务完成
{
  "status": "completed",
  "session_id": "b5f1...",
  "output": "找到了以下三篇…"
}

// 需要人工接管或补充信息
{
  "status": "needs_input",
  "session_id": "b5f1...",
  "reason": "页面出现登录墙，请在弹出的 Chrome 窗口完成登录后再告诉我继续",
  "screenshot": "<base64 jpeg，可选>"
}
```

**超时行为**：若提供 `timeout_seconds` 且到时仍未拿到终止状态，返回 `504`，响应体里带 `session_id`，调用方可以用同一个 `session_id` 再次 POST 继续等待（不会丢状态）。不传则无限等。

### `POST /v1/chat/stream`

启动一次 Agent 任务，并以 SSE 形式返回执行过程事件。

**请求 body** 与 `POST /v1/chat` 相同：

```jsonc
{
  "message": "打开 github.com/trending 并总结前 5 个项目",
  "session_id": "可选；第一次调用不填，服务器会生成并在 start 事件中回传",
  "images": ["data:image/png;base64,...", "..."]   // 可选
}
```

**响应事件示例**：

```text
data: {"type":"start","session_id":"b5f1..."}

data: {"type":"info","message_key":"common.agent_starting","params":{"task":"打开 github.com/trending 并总结前 5 个项目"}}

data: {"type":"info","message_key":"common.executing_action","params":{"tool":"navigate","args":"{\"url\":\"https://github.com/trending\"}"}}

data: {"type":"needs_input","status":"needs_input","reason":"页面需要登录","screenshot":"<base64 jpeg，可选>"}

data: {"type":"done"}
```

事件中的字段来自 Agent 内部消息，调用方应优先根据 `type` 分流处理：

| `type` | 含义 |
| --- | --- |
| `start` | SSE 连接已建立，包含本次会话的 `session_id` |
| `info` | Agent 状态、工具调用、最终完成消息等普通事件 |
| `needs_input` | 需要人工接管或补充信息，可参考 `reason` 和可选截图 |
| `heartbeat` | 长时间无新消息时的保活事件 |
| `error` | Agent 运行异常 |
| `done` | 本次流式任务结束 |

### `GET /v1/chat/{session_id}`

查询会话当前状态：

```jsonc
{
  "session_id": "b5f1...",
  "active": true,                // Agent 还在跑吗
  "waiting_for_human": true,     // 是否阻塞等待人工
  "browser_mode": "local_chrome"
}
```

### `DELETE /v1/chat/{session_id}`

结束会话、取消未完成 Agent 任务、关闭对应浏览器 tab。

### `GET /browser/mode`

返回当前浏览器模式（`local_chrome` / `headless`）。

### `GET /health`

```jsonc
{"ok": true, "browser_mode": "local_chrome", "sessions": 3}
```

---

## cURL 速查

```bash
# 首次请求（自动建 session）
curl -s -X POST http://localhost:8100/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"打开 github.com/trending 截图发给我"}'

# 流式请求（SSE）
curl -N -X POST http://localhost:8100/v1/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"打开 github.com/trending 并总结前 5 个项目"}'

# 用返回的 session_id 继续追加一句
SID=<上一次返回的 session_id>
curl -s -X POST http://localhost:8100/v1/chat \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"message\":\"我已经登录好了，继续\"}"

# 查看状态
curl -s http://localhost:8100/v1/chat/$SID

# 清理
curl -s -X DELETE http://localhost:8100/v1/chat/$SID
```

---

## 注意

- `POST /v1/chat` 是**长轮询**风格：Agent 可能跑好几分钟。调用方 HTTP client 的读超时要给够（或用 `timeout_seconds` 分次拉）。
- `POST /v1/chat/stream` 是**流式**接口，调用方需要按 SSE 协议逐条读取 `data:` 事件。
- 同一 `session_id` 不支持并发 POST——第二个请求会收到 `409 Session already busy`。请顺序调用。
- 同步接口只返回最终结论或需要人工的信号；如果需要中间状态，请使用 `POST /v1/chat/stream`，或者使用主服务的 WebSocket (`/ws/agent`)。
- 浏览器窗口在进程生命周期内持续打开；进程退出时才会关闭。
