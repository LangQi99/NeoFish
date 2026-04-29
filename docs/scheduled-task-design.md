# NeoFish 定时任务 BotSession 详细设计方案

> **状态**: 设计文档
> **版本**: v2.0
> **日期**: 2026-04-29

---

## 目录

1. [架构概览](#1-架构概览)
2. [数据模型](#2-数据模型)
3. [新增文件](#3-新增文件)
4. [修改文件](#4-修改文件)
5. [执行流程](#5-执行流程)
6. [边界情况与错误处理](#6-边界情况与错误处理)
7. [测试计划](#7-测试计划)
8. [实施顺序](#8-实施顺序)

---

## 1. 架构概览

### 1.1 核心思路

**三个新组件，最小侵入现有代码：**

```
┌─────────────────────────────────────────────────────────┐
│  run_all.py (启动时创建 + 连线)                           │
│                                                         │
│  ┌──────────────┐    cron触发     ┌──────────────────┐  │
│  │ SchedulerService │ ──────────→ │ BotSession       │  │
│  │              │    task_queue   │                  │  │
│  │ tasks.json   │                │ session_id:      │  │
│  │ tick(30s)    │                │  "bot:scheduler" │  │
│  └──────┬───────┘                │ Agent Loop (持久)│  │
│         │                        │ 独立的             │  │
│         │ schedule_task()        │  - SessionMemory  │  │
│         │ list_scheduled()       │  - Workspace      │  │
│         │ cancel_scheduled()     │  - 浏览器标签页    │  │
│         │                        └────────┬─────────┘  │
│         │                                 │             │
│  ┌──────┴─────────────────────────┐      │             │
│  │ 其他会话的 Agent Loop           │      │ 结果回调     │
│  │ (Telegram/QQ/Web)              │      │             │
│  │                                │      │             │
│  │ 用户说"每天8点发B站报告"         │      │             │
│  │   → Agent 分析                  │      │             │
│  │   → 调用 schedule_task 工具     │ ─────┘             │
│  │   → SchedulerService.add()     │                    │
│  └────────────────────────────────┘                    │
│                         │                              │
│                         ▼                              │
│              on_task_complete 回调                      │
│              → 路由到平台适配器推送结果                   │
└─────────────────────────────────────────────────────────┘
```

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **最小侵入** | `run_agent_loop` 只新增 1 个可选参数 |
| **复用现有** | 复用 SessionStore、MessageBus、PlaywrightManager、WorkspaceManager |
| **职责分离** | SchedulerService 只管"到没到时间"，BotSession 只管"执行" |
| **平台无关** | BotSession 不依赖任何平台适配器，结果通过回调推回 |

### 1.3 BotSession 与其他会话的对比

| 属性 | 普通会话 | BotSession |
|------|---------|------------|
| session_id | UUID (动态生成) | `"bot:scheduler"` (固定) |
| 消息来源 | 平台适配器 (Telegram/QQ/Web) | SchedulerService 的任务队列 |
| Agent Loop | 每消息一次 | 持久运行，循环消费队列 |
| SessionMemory | 每次任务独立 | 跨任务共享，记录调度状态 |
| finish_task 行为 | 停止循环，emit_info 到用户 | 存储结果，停止循环，回到等待 |
| 浏览器标签页 | 按需创建 | 持久复用 |
| 生命周管理 | platform adapter | run_all.py 启动/销毁 |

---

## 2. 数据模型

### 2.1 ScheduledTask

```python
# scheduler_service.py

from dataclasses import dataclass, field
from typing import Optional
import uuid

@dataclass
class ScheduledTask:
    task_id: str              # UUID，唯一标识
    cron_expr: str            # cron 表达式, e.g. "0 8 * * *"
    description: str          # 人类可读描述, e.g. "每日B站浏览报告"
    prompt: str               # 注入 BotSession 的完整提示词
    source_session_id: str    # 创建者 session_id（结果回传目标）
    source_chat_id: str       # 创建者 chat_id（用于消息路由）
    source_platform: str      # "telegram" | "qq" | "web"
    debug: bool = False       # 是否向源会话输出调试信息
    enabled: bool = True      # 是否启用
    created_at: float = field(default_factory=lambda: __import__("time").time())
    last_run_at: Optional[float] = None
    last_status: Optional[str] = None  # "success" | "failed" | "timeout"
```

### 2.2 持久化格式

文件路径: `data/scheduled_tasks.json`

```json
{
  "tasks": {
    "uuid-1": {
      "task_id": "uuid-1",
      "cron_expr": "0 8 * * *",
      "description": "每日B站浏览报告",
      "prompt": "请打开B站历史记录页面，抓取今日观看视频...",
      "source_session_id": "abc-123",
      "source_chat_id": "telegram:123456",
      "source_platform": "telegram",
      "debug": false,
      "enabled": true,
      "created_at": 1714377600.0,
      "last_run_at": 1714464000.0,
      "last_status": "success"
    }
  }
}
```

### 2.3 BotTaskResult

```python
# bot_session.py

@dataclass
class BotTaskResult:
    task_id: str
    description: str
    status: str           # "success" | "failed"
    summary: str          # finish_task 的 report 参数
    files: list[str]      # finish_task 的 files 参数（workspace 相对路径）
    error: str | None = None
```

---

## 3. 新增文件

### 3.1 `scheduler_service.py` — 调度器

```python
"""
SchedulerService — 定时任务调度引擎

职责：
1. 存储定时任务（JSON 文件持久化）
2. 每秒 tick 检查 cron 表达式
3. 到期时向 BotSession 的任务队列注入消息
4. 维护 last_run_at 和 last_status
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_STORAGE = Path("data/scheduled_tasks.json")

# ── Data ────────────────────────────────────────────────────────

@dataclass
class ScheduledTask:
    task_id: str
    cron_expr: str
    description: str
    prompt: str
    source_session_id: str
    source_chat_id: str
    source_platform: str
    debug: bool = False
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_run_at: Optional[float] = None
    last_status: Optional[str] = None

# ── Service ─────────────────────────────────────────────────────

class SchedulerService:
    def __init__(
        self,
        bot_task_queue: asyncio.Queue,
        storage_path: Path = DEFAULT_STORAGE,
    ):
        self._queue = bot_task_queue      # BotSession 的 asyncio.Queue
        self._path = storage_path
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # ── Persistence ───────────────────────────────────────────

    def _load(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text("utf-8"))
                for t in data.get("tasks", {}).values():
                    task = ScheduledTask(**t)
                    self._tasks[task.task_id] = task
            except Exception:
                logger.exception("Failed to load scheduled tasks")

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"tasks": {tid: t.__dict__ for tid, t in self._tasks.items()}}
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            "utf-8",
        )

    # ── Public API ─────────────────────────────────────────────

    def add(self, task: ScheduledTask) -> str:
        """添加定时任务，返回 task_id"""
        self._tasks[task.task_id] = task
        self._save()
        logger.info("Scheduled task added: %s (%s)", task.description, task.task_id)
        return task.task_id

    def remove(self, task_id: str) -> bool:
        """删除定时任务，返回是否成功"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save()
            return True
        return False

    def get(self, task_id: str) -> Optional[ScheduledTask]:
        return self._tasks.get(task_id)

    def list_by_session(self, session_id: str) -> list[ScheduledTask]:
        """列出某会话创建的所有任务"""
        return [
            t for t in self._tasks.values()
            if t.source_session_id == session_id
        ]

    def list_all(self) -> list[ScheduledTask]:
        return list(self._tasks.values())

    # ── Tick Loop ──────────────────────────────────────────────

    async def start(self):
        self._load()
        self._running = True
        self._task = asyncio.create_task(self._tick(), name="scheduler-tick")
        logger.info("SchedulerService started with %d tasks", len(self._tasks))

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _tick(self):
        """每秒检查一次 cron 匹配"""
        from croniter import croniter
        from datetime import datetime

        while self._running:
            now = datetime.now()
            for task in list(self._tasks.values()):
                if not task.enabled:
                    continue
                try:
                    cron = croniter(task.cron_expr, now)
                    prev = cron.get_prev(datetime)
                    # 如果上次执行时间早于上一次 cron 触发时间，说明到期了
                    if task.last_run_at is None or task.last_run_at < prev.timestamp():
                        await self._trigger(task)
                except Exception:
                    logger.exception("Cron check failed for task %s", task.task_id)

            await asyncio.sleep(1)

    async def _trigger(self, task: ScheduledTask):
        """触发任务，将 prompt 注入 BotSession 队列"""
        logger.info("Triggering scheduled task: %s (%s)", task.description, task.task_id)

        # 构造注入消息
        message = {
            "type": "scheduled_task",
            "task_id": task.task_id,
            "description": task.description,
            "prompt": task.prompt,
            "source_session_id": task.source_session_id,
            "source_chat_id": task.source_chat_id,
            "source_platform": task.source_platform,
            "debug": task.debug,
        }

        await self._queue.put(message)
        task.last_run_at = time.time()
        self._save()
```

**依赖**: `croniter` — Python cron 表达式解析库，`pip install croniter`

**设计决策**：
- 每秒 tick 一次，精度够用（不需要毫秒级）
- 用 `get_prev()` 判断触发：如果 `last_run_at < 上一次 cron 触发时间`，说明该触发了
- 不自己计算 cron 的下一次触发时间，完全交给 croniter

### 3.2 `bot_session.py` — BotSession

```python
"""
BotSession — 定时任务专用固定会话

一个持久运行的 Agent Loop，从 asyncio.Queue 消费 ScheduledTask，
每个任务调用 run_agent_loop 执行，完成后通过回调推送结果到源会话。
"""

import asyncio
import logging
from pathlib import Path
from dataclasses import dataclass

from playwright_manager import PlaywrightManager
from workspace_manager import WorkspaceManager
from memory.session_memory import SessionMemory
from tool_registry import ToolExecutionResult, ToolRegistry

logger = logging.getLogger(__name__)

BOT_SESSION_ID = "bot:scheduler"
BOT_WORKSPACE = Path("workspaces/bot_scheduler")

# ── System Prompt ─────────────────────────────────────────────

BOT_SYSTEM_PROMPT = f"""You are NeoFish BotSession — a dedicated scheduled-task executor.

## Your Role
You receive scheduled task prompts and execute them autonomously.
You have the same tools as any NeoFish agent: browser control, file operations,
bash commands, task tracking, and knowledge search.

## Core Rules
1. Execute ALL requirements in the scheduled task prompt completely.
2. When done, call `finish_task` with a clear summary in the `report` parameter.
3. If you generated files (reports, screenshots, PDFs), list their paths in the
   `files` parameter of finish_task.
4. If the task cannot be completed (site inaccessible, insufficient info, etc.),
   call `finish_task` with the failure reason in the report.
5. After finish_task, do NOT do anything else — your job is done.
6. Do NOT ask for human confirmation or assistance — make all decisions yourself.

## Workspace
Your workspace is at: {BOT_WORKSPACE.resolve()}
All files you create go here. Use relative paths.

## Important
- You have a 10-minute practical time limit per task.
- Do not modify files from previous tasks unless the current task requires it.
- Each task is independent — do not rely on browser/login state from prior tasks.
"""

# ── Result ─────────────────────────────────────────────────────

@dataclass
class BotTaskResult:
    task_id: str
    description: str
    status: str      # "success" | "failed" | "error"
    summary: str
    files: list[str]
    error: str | None = None

# ── Callback type ──────────────────────────────────────────────

# async def on_complete(result: BotTaskResult, source_session_id: str, source_chat_id: str, source_platform: str, debug: bool) -> None
OnTaskComplete = Callable[[BotTaskResult, str, str, str, bool], Awaitable[None]]

# ── BotSession ─────────────────────────────────────────────────

class BotSession:
    def __init__(
        self,
        task_queue: asyncio.Queue,
        pm: PlaywrightManager,
        on_complete: OnTaskComplete,
        workspace: WorkspaceManager | None = None,
    ):
        self._queue = task_queue
        self._pm = pm
        self._on_complete = on_complete
        self._workspace = workspace or WorkspaceManager(BOT_WORKSPACE, strict=False)
        self._session_memory = SessionMemory(session_id=BOT_SESSION_ID)
        self._running = False
        self._current_task_meta: dict | None = None

    @property
    def session_id(self) -> str:
        return BOT_SESSION_ID

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Lifecycle ──────────────────────────────────────────

    async def start(self):
        self._running = True
        logger.info("BotSession started (session_id=%s)", BOT_SESSION_ID)
        await self._loop()

    async def stop(self):
        self._running = False
        logger.info("BotSession stopped")

    async def _loop(self):
        """主循环：等待任务 → 执行 → 回调 → 重复"""
        while self._running:
            try:
                task_meta = await self._queue.get()
            except asyncio.CancelledError:
                break

            if task_meta is None:  # 哨兵，用于停止
                break

            self._current_task_meta = task_meta
            result = await self._execute_task(task_meta)
            self._current_task_meta = None

            # 回调推送结果
            try:
                await self._on_complete(
                    result,
                    task_meta["source_session_id"],
                    task_meta.get("source_chat_id", ""),
                    task_meta.get("source_platform", "unknown"),
                    task_meta.get("debug", False),
                )
            except Exception:
                logger.exception("on_complete callback failed")

    # ── Task Execution ──────────────────────────────────────

    async def _execute_task(self, task_meta: dict) -> BotTaskResult:
        """执行单个定时任务，返回结果"""
        from agent import run_agent_loop, _create_tool_registry

        task_id = task_meta["task_id"]
        description = task_meta["description"]
        prompt = task_meta["prompt"]
        debug = task_meta.get("debug", False)

        logger.info("BotSession executing task: %s (%s)", description, task_id)

        # 用于捕获 finish_task 的结果
        finish_result: dict = {}

        async def _bot_finish_task(args: dict) -> ToolExecutionResult:
            finish_result["report"] = args.get("report", "")
            finish_result["files"] = args.get("files", [])
            if debug:
                logger.debug("BotSession finish_task: report=%s, files=%s",
                             finish_result["report"][:200], finish_result["files"])
            return ToolExecutionResult(output="Task completed.", finished=True)

        # 空 emit 回调 — BotSession 不需要向用户推送中间消息
        async def _noop_emit(msg):
            if debug:
                logger.debug("BotSession emit: %s", str(msg)[:200])

        async def _noop_action(reason, image=None):
            logger.warning("BotSession got action_required, auto-deny: %s", reason)

        async def _noop_image(desc, img):
            pass  # BotSession 不发送截图给用户

        async def _noop_file(path, desc):
            pass  # 文件通过 finish_task 的 files 参数输出

        try:
            await run_agent_loop(
                pm=self._pm,
                user_instruction=prompt,
                ws_send_msg=_noop_emit,
                ws_request_action=_noop_action,
                ws_send_image=_noop_image,
                ws_send_file=_noop_file,
                session_id=BOT_SESSION_ID,
                session_memory=self._session_memory,
                tool_overrides={"finish_task": _bot_finish_task},
                message_center=None,  # BotSession 不用 MessageBus
            )

            report = finish_result.get("report", "(no report)")
            files = finish_result.get("files", [])

            # 判断成功/失败
            status = "success"
            if any(kw in report.lower() for kw in ["fail", "error", "unable", "cannot"]):
                status = "failed"

            return BotTaskResult(
                task_id=task_id,
                description=description,
                status=status,
                summary=report,
                files=files,
            )

        except Exception as e:
            logger.exception("BotSession task execution error: %s", task_id)
            return BotTaskResult(
                task_id=task_id,
                description=description,
                status="error",
                summary=str(e),
                files=[],
                error=str(e),
            )
```

**设计决策**：
- `emit_info` / `emit_action_required` 等回调全部换成 noop — BotSession 不需要实时推送中间状态
- `finish_task` 被重写，捕获 report 和 files 到闭包变量
- 异常兜底：即使 run_agent_loop 崩溃，也返回 BotTaskResult 并继续处理下一个任务
- 每个任务都是一次独立的 `run_agent_loop` 调用，共享同一个 `SessionMemory`

---

## 4. 修改文件

### 4.1 `agent.py` — 新增 3 个工具 + `tool_overrides` 参数

#### 4.1.1 `run_agent_loop` 新增 `tool_overrides` 参数

```python
async def run_agent_loop(
    pm: PlaywrightManager,
    user_instruction: str,
    ws_send_msg=None,
    ws_request_action=None,
    ws_send_image=None,
    ws_send_file=None,
    message_center: MessageCenter | None = None,
    images: list = [],
    history_messages: list = [],
    uploaded_files: list = [],
    session_store=None,
    session_id: str = None,
    web_queue_getter=None,
    web_session_id: str = None,
    cancel_event: asyncio.Event = None,
    session_memory: SessionMemory | None = None,
    save_session_memory_fn=None,
    tool_overrides: dict[str, Callable] = None,  # ← NEW
):
```

在 `_create_tool_registry` 调用之后，应用 overrides：

```python
    tool_registry = _create_tool_registry(
        pm=pm,
        page=page,
        effective_session_id=effective_session_id,
        auto_root_task=auto_root_task,
        emit_info=emit_info,
        emit_action_required=emit_action_required,
        emit_image=emit_image,
        emit_file=emit_file,
    )
    # NEW: apply tool overrides
    if tool_overrides:
        for name, handler in tool_overrides.items():
            tool_registry.register(name, handler)
```

**侵入度**: 1 个可选参数 + 3 行代码

#### 4.1.2 `finish_task` 工具定义新增 `files` 参数

```python
{
    "name": "finish_task",
    "description": "Call this tool when the final objective is fully accomplished. Pass the final report to the user.",
    "input_schema": {
        "type": "object",
        "properties": {
            "report": {
                "type": "string",
                "description": "Markdown formatted summary",
            },
            "files": {                                            # ← NEW
                "type": "array",
                "items": {"type": "string"},
                "description": "List of generated file paths (relative to workspace) to send to user",
            },
        },
        "required": ["report"],
    },
},
```

#### 4.1.3 新增 3 个工具定义（添加到 `TOOLS` 列表）

```python
{
    "name": "schedule_task",
    "description": (
        "Add a scheduled/recurring task. The bot will execute the given prompt "
        "at the specified cron schedule. Results will be sent back to this conversation. "
        "Use this for reminders, daily reports, periodic checks, etc. "
        "Cron format: 'minute hour day month weekday' (e.g. '0 8 * * *' = daily at 8am)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cron": {
                "type": "string",
                "description": "Cron expression. e.g. '0 8 * * *' = 8am daily, '0 10 * * 1' = 10am every Monday",
            },
            "prompt": {
                "type": "string",
                "description": "The full prompt to send to the bot at the scheduled time. Include all necessary details for the task.",
            },
            "description": {
                "type": "string",
                "description": "Short human-readable description (e.g. 'Daily Bilibili report')",
            },
            "debug": {
                "type": "boolean",
                "description": "If true, the raw prompt will be sent to this conversation when the task triggers. Default: false",
            },
        },
        "required": ["cron", "prompt", "description"],
    },
},
{
    "name": "list_scheduled_tasks",
    "description": "List all scheduled tasks created in this conversation, with their status.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
},
{
    "name": "cancel_scheduled_task",
    "description": "Cancel a previously scheduled task.",
    "input_schema": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The task ID to cancel (from list_scheduled_tasks)",
            },
        },
        "required": ["task_id"],
    },
},
```

#### 4.1.4 在 `_create_tool_registry` 中注册 3 个工具的处理函数

需要在 `_create_tool_registry` 的入参中新增 `scheduler_service` 和 `source_session_info`：

```python
def _create_tool_registry(
    *,
    pm: PlaywrightManager,
    page,
    effective_session_id: str,
    auto_root_task: dict | None,
    emit_info,
    emit_action_required,
    emit_image,
    emit_file,
    scheduler_service=None,       # ← NEW: SchedulerService 实例
    source_meta: dict = None,     # ← NEW: {session_id, chat_id, platform}
) -> ToolRegistry:
```

然后在 `_create_tool_registry` 末尾新增三个处理函数：

```python
    # ── Scheduled Task Tools ──────────────────────────────────

    async def _schedule_task(args: dict) -> ToolExecutionResult:
        if scheduler_service is None:
            return ToolExecutionResult(
                output="Error: SchedulerService is not available. "
                       "Scheduled tasks are only supported in run_all.py mode."
            )

        from scheduler_service import ScheduledTask
        import uuid

        task = ScheduledTask(
            task_id=str(uuid.uuid4()),
            cron_expr=args["cron"],
            description=args["description"],
            prompt=args["prompt"],
            source_session_id=source_meta.get("session_id", effective_session_id) if source_meta else effective_session_id,
            source_chat_id=source_meta.get("chat_id", "") if source_meta else "",
            source_platform=source_meta.get("platform", "unknown") if source_meta else "web",
            debug=args.get("debug", False),
        )
        scheduler_service.add(task)

        return ToolExecutionResult(
            output=(
                f"已添加定时任务：\n"
                f"- 描述：{task.description}\n"
                f"- Cron：{task.cron_expr}\n"
                f"- 任务ID：{task.task_id}\n"
                f"- Debug模式：{'开启' if task.debug else '关闭'}"
            )
        )

    async def _list_scheduled_tasks(args: dict) -> ToolExecutionResult:
        if scheduler_service is None:
            return ToolExecutionResult(output="SchedulerService not available.")
        tasks = scheduler_service.list_by_session(
            source_meta.get("session_id", effective_session_id) if source_meta else effective_session_id
        )
        if not tasks:
            return ToolExecutionResult(output="当前没有定时任务。")
        lines = ["当前定时任务：", ""]
        for i, t in enumerate(tasks, 1):
            status_icon = "✅" if t.last_status == "success" else ("❌" if t.last_status else "⏳")
            last_run = f"上次执行：{t.last_run_at}" if t.last_run_at else "尚未执行"
            lines.append(f"[{i}] {status_icon} {t.description}")
            lines.append(f"    Cron: {t.cron_expr} | {last_run}")
            lines.append(f"    ID: {t.task_id}")
            lines.append("")
        return ToolExecutionResult(output="\n".join(lines))

    async def _cancel_scheduled_task(args: dict) -> ToolExecutionResult:
        if scheduler_service is None:
            return ToolExecutionResult(output="SchedulerService not available.")
        ok = scheduler_service.remove(args["task_id"])
        if ok:
            return ToolExecutionResult(output=f"已取消定时任务 {args['task_id']}")
        return ToolExecutionResult(output=f"未找到定时任务 {args['task_id']}")

    registry.register("schedule_task", _schedule_task)
    registry.register("list_scheduled_tasks", _list_scheduled_tasks)
    registry.register("cancel_scheduled_task", _cancel_scheduled_task)
```

**注意**：`_create_tool_registry` 会被所有调用路径使用（`main.py`、`_agent_runner.py`、`bot_session.py`）。新增参数都带默认值 `None`，保证向后兼容。

### 4.2 `session.py` — 新增 `reverse_lookup` 方法

```python
def reverse_lookup(self, session_id: str) -> tuple[str, str] | None:
    """
    根据 session_id 反查其所属平台和 chat_id。
    返回 (platform, chat_id) 或 None。
    """
    # 遍历 _reverse 找匹配的 session_id，提取 platform
    for rev_key, chat_id in self._reverse.items():
        # rev_key format: "{platform}:{session_id}"
        if rev_key.endswith(f":{session_id}"):
            platform = rev_key.rsplit(":", 1)[0]
            return platform, chat_id

    # 如果没有 mapping 但有 queue（可能是 web 创建的 session）
    if session_id in self._queues:
        return "web", session_id

    return None
```

### 4.3 `run_all.py` — 启动时创建 BotSession + SchedulerService

```python
"""
run_all.py — Launch all NeoFish platform adapters + BotSession + SchedulerService
"""

import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _run_web(playwright_manager=None):
    """Start the FastAPI/uvicorn web server."""
    import uvicorn
    from config import WEB_HOST, WEB_PORT

    config = uvicorn.Config(
        "main:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=False,
        log_level="info",
    )
    server = uvicorn.Server(config)
    logger.info("Starting Web adapter on %s:%d…", WEB_HOST, WEB_PORT)
    await server.serve()


async def _run_telegram(pm, session_store):
    """Start the Telegram bot adapter."""
    from config import TELEGRAM_BOT_TOKEN
    if not TELEGRAM_BOT_TOKEN:
        logger.info("Telegram adapter skipped (TELEGRAM_BOT_TOKEN not set).")
        return

    from platforms.telegram import TelegramAdapter
    from _agent_runner import make_message_handler

    adapter = TelegramAdapter(session_store=session_store)
    adapter.on_message = make_message_handler(adapter, pm, session_store)

    logger.info("Starting Telegram adapter…")
    await adapter.start()

    try:
        await asyncio.Event().wait()
    finally:
        await adapter.stop()

    return adapter  # 返回引用


async def _run_qq(pm, session_store):
    """Start the QQ bot adapter."""
    from config import QQ_WS_URL
    if not QQ_WS_URL:
        logger.info("QQ adapter skipped (QQ_WS_URL not set).")
        return

    from platforms.qq import QQAdapter
    from _agent_runner import make_message_handler

    adapter = QQAdapter(session_store=session_store)
    adapter.on_message = make_message_handler(adapter, pm, session_store)

    logger.info("Starting QQ adapter…")
    await adapter.start()

    try:
        await asyncio.Event().wait()
    finally:
        await adapter.stop()

    return adapter  # 返回引用


# ── Result Callback Factory ────────────────────────────────────

def _make_result_callback(session_store, telegram_adapter, qq_adapter, message_bus):
    """创建 BotSession 的结果回调函数"""

    async def on_bot_task_complete(
        result,           # BotTaskResult
        source_session_id: str,
        source_chat_id: str,
        source_platform: str,
        debug: bool,
    ):
        # 格式化结果消息
        status_icon = "✅" if result.status == "success" else "❌"
        text = (
            f"📅 定时任务【{result.description}】已完成\n"
            f"{status_icon} 状态：{result.status}\n"
            f"────────────────────────\n"
            f"{result.summary}"
        )

        if debug:
            text += f"\n\n🔍 [Debug] 任务ID: {result.task_id}"

        if result.files:
            text += f"\n\n📎 生成文件: {', '.join(result.files)}"

        if result.error:
            text += f"\n\n⚠️ 错误: {result.error}"

        # 按平台路由
        if source_platform == "telegram" and telegram_adapter:
            await telegram_adapter.send_message(source_session_id, text)
            for f in result.files:
                try:
                    await telegram_adapter.send_file(source_session_id, f, "")
                except Exception:
                    logger.exception("Failed to send file %s", f)

        elif source_platform == "qq" and qq_adapter:
            await qq_adapter.send_message(source_session_id, text)
            for f in result.files:
                try:
                    await qq_adapter.send_file(source_session_id, f, "")
                except Exception:
                    logger.exception("Failed to send file %s", f)

        elif source_platform == "web":
            # Web: 通过 MessageBus 推送
            if message_bus:
                from message_center import BusEvent
                await message_bus.publish(BusEvent(
                    session_id=source_session_id,
                    event_type="scheduled_result",
                    payload={
                        "task_id": result.task_id,
                        "description": result.description,
                        "status": result.status,
                        "summary": result.summary,
                        "files": result.files,
                        "debug": debug,
                    },
                ))

        else:
            logger.warning("Unknown source_platform for result callback: %s", source_platform)

    return on_bot_task_complete


# ── Main ────────────────────────────────────────────────────────

async def main():
    from playwright_manager import PlaywrightManager
    from session import session_store
    from bot_session import BotSession
    from scheduler_service import SchedulerService
    from message_center import message_bus

    # 共享的 PlaywrightManager
    pm = PlaywrightManager()
    await pm.start()

    # 创建 BotSession 的任务队列
    bot_queue = asyncio.Queue()

    # 启动 SchedulerService
    scheduler = SchedulerService(bot_task_queue=bot_queue)
    await scheduler.start()

    # 启动平台适配器
    tg_task = asyncio.create_task(_run_telegram(pm, session_store), name="telegram")
    qq_task = asyncio.create_task(_run_qq(pm, session_store), name="qq")
    web_task = asyncio.create_task(_run_web(pm), name="web")

    # 等待平台适配器初始化（简单延迟，让它们先 start）
    await asyncio.sleep(2)

    # 获取适配器引用（用于结果回调）
    # 注意：_run_telegram 阻塞在 Event().wait()，我们需要在内部获取引用
    # 简化方案：在 _run_telegram 内部注册到全局变量
    # 更优方案：使用 asyncio.Queue 或共享状态传递引用

    # 创建结果回调
    on_complete = _make_result_callback(
        session_store=session_store,
        telegram_adapter=None,   # ← 需要从 _run_telegram 获取
        qq_adapter=None,         # ← 需要从 _run_qq 获取
        message_bus=message_bus,
    )

    # 创建并启动 BotSession
    bot = BotSession(
        task_queue=bot_queue,
        pm=pm,
        on_complete=on_complete,
    )
    bot_task = asyncio.create_task(bot.start(), name="bot-session")

    # 将所有平台适配器、BotSession 注册到一个共享上下文
    # （方便工具处理函数获取 scheduler_service）

    try:
        await asyncio.gather(tg_task, qq_task, web_task, bot_task)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down…")
        await bot.stop()
        await scheduler.stop()
        await pm.stop()
        for t in [tg_task, qq_task, web_task, bot_task]:
            t.cancel()
        await asyncio.gather(tg_task, qq_task, web_task, bot_task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
```

**注意**：上面 `_run_telegram` 需要改为返回 adapter 引用，而不是永远阻塞在 `Event().wait()`。这需要调整适配器启动方式。有两种方案：

**方案 A（推荐）**：用 `asyncio.Event` 控制 adapter 生命周期

```python
async def _run_telegram(pm, session_store):
    """返回 (adapter, done_event)"""
    from platforms.telegram import TelegramAdapter
    from _agent_runner import make_message_handler

    adapter = TelegramAdapter(session_store=session_store)
    adapter.on_message = make_message_handler(adapter, pm, session_store)

    await adapter.start()
    logger.info("Telegram adapter started")

    done = asyncio.Event()
    try:
        await done.wait()  # 等待外部信号停止
    finally:
        await adapter.stop()

    return adapter
```

在 `main()` 中：
```python
tg_adapter = None
qq_adapter = None

# ...

# 等待适配器启动后获取引用
await asyncio.sleep(3)

# 重新创建回调（用实际引用）
on_complete = _make_result_callback(
    session_store=session_store,
    telegram_adapter=tg_adapter,
    qq_adapter=qq_adapter,
    message_bus=message_bus,
)
bot.on_complete = on_complete  # 或者通过方法更新
```

**方案 B（更简单）**：适配器注册到全局 dict

```python
# 全局
platform_adapters: dict[str, "PlatformAdapter"] = {}

# 在 _run_telegram 中:
platform_adapters["telegram"] = adapter

# 在 _make_result_callback 中:
tg = platform_adapters.get("telegram")
```

**建议采用方案 B**，更直接。

### 4.4 `_agent_runner.py` — 传递 scheduler_service 和 source_meta

在 `make_message_handler` 中，需要获取 `scheduler_service` 引用和构造 `source_meta`，传递给 `run_agent_loop`。

修改点：

```python
def make_message_handler(adapter, pm, session_store, workdir=None, scheduler_service=None):
    # ... 
    async def on_message(unified_msg):
        # ...
        source_meta = {
            "session_id": session_id,
            "chat_id": unified_msg.user_id,
            "platform": unified_msg.platform,
        }
        
        await run_agent_loop(
            # ... 已有参数 ...
            scheduler_service=scheduler_service,    # NEW
            source_meta=source_meta,                # NEW
        )
```

同时 `run_agent_loop` 需要新增 `scheduler_service` 和 `source_meta` 参数并下传到 `_create_tool_registry`。

### 4.5 `main.py` — Web 端无需 SchedulerService

Web 端的 `run_agent_loop` 调用传入 `scheduler_service=None`（默认），工具处理函数会返回 "SchedulerService not available" 错误。这是预期行为 — Web 端不适合定时任务（agent loop 不持久）。

如需支持，可以在 `main.py` 也创建 SchedulerService，但需要 Web 端 agent loop 长期运行（目前不是）。

---

## 5. 执行流程

### 5.1 创建任务

```
用户 (Telegram) "每天早上八点帮我发一份B站浏览报告"
  │
  ▼
Agent Loop (用户会话)
  │  分析意图
  │  构造 cron="0 8 * * *"
  │  构造 prompt="请打开 B站历史记录页面...生成PDF报告"
  │
  ▼
调用 schedule_task 工具
  │  handler → SchedulerService.add(task)
  │  → 写入 data/scheduled_tasks.json
  │
  ▼
返回: "已添加定时任务：每日B站浏览报告 (Cron: 0 8 * * *)"
```

### 5.2 触发任务

```
SchedulerService._tick()
  │  croniter.match("0 8 * * *", now) → True
  │  last_run_at 早于上一次 cron 时间 → 触发
  │
  ▼
await bot_queue.put({
    type: "scheduled_task",
    task_id: "...",
    description: "每日B站浏览报告",
    prompt: "请打开B站历史记录页面...",
    source_session_id: "...",
    ...
})
  │
  ▼
BotSession._loop() → await bot_queue.get()
  │
  ▼
BotSession._execute_task(task_meta)
  │  await run_agent_loop(
  │      pm=..., 
  │      user_instruction=prompt,
  │      session_id="bot:scheduler",
  │      tool_overrides={"finish_task": _bot_finish_task},
  │  )
  │
  │  Agent 执行: navigate→snapshot→extract→write_file→finish_task
  │
  ▼
_bot_finish_task 捕获:
    report="已生成今日B站浏览报告，共15个视频..."
    files=["bilibili_report_2026-04-29.pdf"]
  │
  ▼
BotTaskResult(status="success", summary="...", files=[...])
```

### 5.3 结果回传

```
BotSession._loop()
  │
  ▼
await on_complete(result, source_session_id, source_chat_id, source_platform, debug)
  │
  ▼
_make_result_callback → 路由:
  │
  ├─ Telegram: telegram_adapter.send_message(session_id, text)
  │             telegram_adapter.send_file(session_id, "报告.pdf")
  │
  ├─ QQ: qq_adapter.send_message(session_id, text)
  │       qq_adapter.send_file(session_id, "报告.pdf")
  │
  └─ Web: message_bus.publish(scheduled_result, ...)
           → WebAdapter._handle_bus_event
           → 追加到 messages.jsonl
           → WebSocket 推送（如果在线）
```

### 5.4 Debug 模式流程

```
如果 task.debug == True:

1. SchedulerService._trigger() 时:
   → 向源会话注入消息:
     "🔍 [定时任务 Debug] 每日B站浏览报告 已触发
      原始提示词:
      ────────────────────────
      请打开B站历史记录页面..."
   (通过 session_store.enqueue_message)

2. BotSession 执行时:
   → _noop_emit 会记录日志（debug level）
   → _bot_finish_task 会记录日志

3. on_complete 回调时:
   → 结果消息中包含额外信息
```

---

## 6. 边界情况与错误处理

### 6.1 会话不存在

**问题**：用户创建了定时任务，但源会话已被删除（Web session 过期、QQ 群退出等）

**处理**：
- `on_complete` 回调中，`reverse_lookup` 返回 None
- 记录日志，静默丢弃结果
- 后续可扩展：连续 N 次回传失败后自动 disable 任务

### 6.2 BotSession 任务超时

**问题**：任务跑太长时间（例如网站加载慢，agent 陷入循环）

**处理**：
- `run_agent_loop` 已有 `max_steps` 限制（9999999），不需要额外超时
- 如果 agent 在等待（如 request_human_assistance），BotSession 的 `_noop_action` 直接拒绝
- 后续可扩展：`asyncio.wait_for(run_agent_loop, timeout=600)` 包裹 10 分钟超时

### 6.3 同时触发多个任务

**问题**：两个 cron 表达式同时到期（如 8:00 有 A 和 B）

**处理**：
- `SchedulerService._tick()` 顺序检查，两个消息先后 push 到 bot_queue
- BotSession 的 `_loop()` 顺序消费，FIFO 执行
- 不需要额外加锁

### 6.4 服务重启

**问题**：服务重启时，正在执行的任务丢失

**处理**：
- 服务重启不会恢复正在进行的任务（无伤大雅，下次 cron 触发重新执行）
- `data/scheduled_tasks.json` 持久化，重启后任务列表不丢失
- `last_run_at` 记录在上次触发时（push 到队列时），不是执行完成时
  - 这意味着如果 BotSession 崩溃，任务已经在队列中，但没执行完
  - 影响：下次 cron 触发时会再次执行（因为 last_run_at < prev_cron_time）
  - 这是可接受的行为：至多重跑一次，不会漏跑

### 6.5 浏览器标签页复用

**问题**：上一个任务留下的登录状态、页面状态影响下一个任务

**处理**：
- 每个任务的 prompt 应该包含完整的起始步骤（如"打开 https://bilibili.com，登录..."）
- BotSession 的 System Prompt 已说明 "Each task is independent"
- 如果需要在 prompt 中显式加入 `navigate` 作为第一步
- 后续可扩展：任务执行前自动 `navigate("about:blank")`

### 6.6 croniter 不可用

**问题**：未安装 croniter 库

**处理**：
- `SchedulerService._tick()` 中 `from croniter import croniter` 会抛出 ImportError
- 捕获并记录错误，SchedulerService 启动失败但不影响其他组件
- 在 `run_all.py` 的 main 中检查并给出友好提示

---

## 7. 测试计划

### 7.1 单元测试

| 测试 | 文件 | 说明 |
|------|------|------|
| `test_scheduler_add_remove` | `tests/test_scheduler.py` | 添加/删除/查询任务 |
| `test_scheduler_persistence` | `tests/test_scheduler.py` | 重启后任务恢复 |
| `test_scheduler_cron_match` | `tests/test_scheduler.py` | cron 匹配逻辑（用固定时间）|
| `test_bot_session_execute` | `tests/test_bot_session.py` | mock run_agent_loop，验证结果捕获 |
| `test_bot_session_queue_serial` | `tests/test_bot_session.py` | 验证串行执行（同时 push 两个任务）|
| `test_reverse_lookup` | `tests/test_session.py` | SessionStore.reverse_lookup |
| `test_tool_handlers` | `tests/test_schedule_tools.py` | schedule_task/list/cancel 处理函数 |

### 7.2 集成测试

| 测试 | 说明 |
|------|------|
| **端到端定时触发** | 设定 cron 为当前时间 + 1 分钟，验证 BotSession 收到并执行 |
| **结果回传 Telegram** | Mock TelegramAdapter，验证 on_complete 调用 send_message |
| **结果回传 QQ** | Mock QQAdapter，验证 on_complete 调用 send_message |
| **Debug 模式** | 验证 debug=true 时源会话收到额外消息 |
| **并发任务** | 设定两个同时间 cron，验证串行执行 |
| **失败重试** | Agent 调用 finish_task 报告失败，验证 last_status 更新 |

### 7.3 手动测试

1. 启动 `python run_all.py`
2. 在 Telegram 中发送："一分钟后告诉我时间" → agent 调用 schedule_task(cron="...", prompt="查看当前时间并 finish_task")
3. 等待 1 分钟，观察是否收到结果
4. 发送 "列出我的定时任务" → agent 调用 list_scheduled_tasks
5. 发送 "取消那个任务" → agent 调用 cancel_scheduled_task

---

## 8. 实施顺序

| 步骤 | 文件 | 内容 | 预估耗时 |
|------|------|------|----------|
| 1 | `session.py` | 新增 `reverse_lookup()` | 10 min |
| 2 | `scheduler_service.py` | 完整实现 + JSON 持久化 | 45 min |
| 3 | `bot_session.py` | 完整实现 | 30 min |
| 4 | `agent.py` | 3 个工具定义 + 处理函数 + tool_overrides 参数 | 30 min |
| 5 | `tool_registry.py` | 不变 | 0 |
| 6 | `_agent_runner.py` | 传递 scheduler_service + source_meta | 10 min |
| 7 | `run_all.py` | BotSession + SchedulerService 创建和连线 | 30 min |
| 8 | `requirements.txt` | 添加 croniter 依赖 | 2 min |
| 9 | 测试 | 单元测试 + 手动验证 | 60 min |

**总预估**：约 3.5 小时

---

## 附录 A：依赖项

```
croniter>=2.0.0
```

已存在依赖（无需新增）：
- `asyncio`（标准库）
- `uuid`（标准库）
- `json`（标准库）
- `dataclasses`（标准库）

## 附录 B：工具一览

| 工具名 | 可用范围 | 描述 |
|--------|---------|------|
| `schedule_task` | 所有平台 | 添加定时任务 |
| `list_scheduled_tasks` | 所有平台 | 列出当前会话的定时任务 |
| `cancel_scheduled_task` | 所有平台 | 取消定时任务 |
