"""
BotSession — 定时任务专用固定会话

一个持久运行的 Agent Loop，从 asyncio.Queue 消费 TaskTrigger，
每个任务调用 run_agent_loop 执行，完成后通过回调推送结果到源会话。
"""

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable

from playwright_manager import PlaywrightManager
from workspace_manager import WorkspaceManager
from memory.session_memory import SessionMemory
from tool_registry import ToolExecutionResult
from scheduled_task import BotTaskResult, TaskTrigger

logger = logging.getLogger(__name__)

BOT_SESSION_ID = "bot:scheduler"
BOT_WORKSPACE = Path("workspaces/bot_scheduler")

# ── Callback type ──────────────────────────────────────────────

OnTaskComplete = Callable[
    [BotTaskResult, str, str, str, bool],  # result, source_session_id, source_chat_id, source_platform, debug
    Awaitable[None],
]

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
        self._current_trigger: TaskTrigger | None = None

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
        while self._running:
            try:
                trigger = await self._queue.get()
            except asyncio.CancelledError:
                break

            if trigger is None:
                break

            self._current_trigger = trigger
            result = await self._execute_task(trigger)
            self._current_trigger = None

            try:
                await self._on_complete(
                    result,
                    trigger.source_session_id,
                    trigger.source_chat_id,
                    trigger.source_platform,
                    trigger.debug,
                )
            except Exception:
                logger.exception("on_complete callback failed")

    # ── Task Execution ──────────────────────────────────────

    async def _execute_task(self, trigger: TaskTrigger) -> BotTaskResult:
        from agent import run_agent_loop

        logger.info(
            "BotSession executing task: %s (%s)",
            trigger.description,
            trigger.task_id,
        )

        finish_result: dict = {}

        async def _bot_finish_task(args: dict) -> ToolExecutionResult:
            finish_result["report"] = args.get("report", "")
            finish_result["files"] = args.get("files", [])
            if trigger.debug:
                logger.debug(
                    "BotSession finish_task: report=%s, files=%s",
                    str(finish_result["report"])[:200],
                    finish_result["files"],
                )
            return ToolExecutionResult(output="Task completed.", finished=True)

        async def _noop_emit(msg):
            if trigger.debug:
                logger.debug("BotSession emit: %s", str(msg)[:200])

        async def _noop_action(reason, image=None):
            logger.warning("BotSession got action_required, auto-deny: %s", reason)

        async def _noop_image(desc, img):
            pass

        async def _noop_file(path, desc):
            pass

        try:
            await run_agent_loop(
                pm=self._pm,
                user_instruction=trigger.prompt,
                ws_send_msg=_noop_emit,
                ws_request_action=_noop_action,
                ws_send_image=_noop_image,
                ws_send_file=_noop_file,
                session_id=BOT_SESSION_ID,
                session_memory=self._session_memory,
                tool_overrides={"finish_task": _bot_finish_task},
                message_center=None,
            )

            report = finish_result.get("report", "(no report)")
            files = finish_result.get("files", [])

            status = "success"
            if any(
                kw in report.lower()
                for kw in ["fail", "error", "unable", "cannot"]
            ):
                status = "failed"

            return BotTaskResult(
                task_id=trigger.task_id,
                description=trigger.description,
                status=status,
                summary=report,
                files=files,
            )

        except Exception as e:
            logger.exception("BotSession task execution error: %s", trigger.task_id)
            return BotTaskResult(
                task_id=trigger.task_id,
                description=trigger.description,
                status="error",
                summary=str(e),
                files=[],
                error=str(e),
            )
