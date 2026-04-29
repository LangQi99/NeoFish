"""
SchedulerService — 定时任务调度引擎

职责：
1. 存储定时任务（JSON 文件持久化）
2. 每秒 tick 检查 cron 表达式
3. 到期时向 BotSession 的任务队列注入 TaskTrigger
4. 维护 last_run_at 和 last_status
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from scheduled_task import ScheduledTask, TaskTrigger

logger = logging.getLogger(__name__)

DEFAULT_STORAGE = Path("data/scheduled_tasks.json")


class SchedulerService:
    def __init__(
        self,
        bot_task_queue: asyncio.Queue,
        storage_path: Path = DEFAULT_STORAGE,
    ):
        self._queue = bot_task_queue
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
        data = {"tasks": {}}
        for tid, t in self._tasks.items():
            d = {
                "task_id": t.task_id,
                "cron_expr": t.cron_expr,
                "description": t.description,
                "prompt": t.prompt,
                "source_session_id": t.source_session_id,
                "source_chat_id": t.source_chat_id,
                "source_platform": t.source_platform,
                "debug": t.debug,
                "enabled": t.enabled,
                "created_at": t.created_at,
                "last_run_at": t.last_run_at,
                "last_status": t.last_status,
            }
            data["tasks"][tid] = d
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            "utf-8",
        )

    # ── Public API ─────────────────────────────────────────────

    def add(self, task: ScheduledTask) -> str:
        self._tasks[task.task_id] = task
        self._save()
        logger.info("Scheduled task added: %s (%s)", task.description, task.task_id)
        return task.task_id

    def remove(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save()
            return True
        return False

    def get(self, task_id: str) -> Optional[ScheduledTask]:
        return self._tasks.get(task_id)

    def list_by_session(self, session_id: str) -> list[ScheduledTask]:
        return [
            t for t in self._tasks.values()
            if t.source_session_id == session_id
        ]

    def list_all(self) -> list[ScheduledTask]:
        return list(self._tasks.values())

    # ── Lifecycle ──────────────────────────────────────────────

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
        logger.info("SchedulerService stopped")

    # ── Tick Loop ──────────────────────────────────────────────

    async def _tick(self):
        from croniter import croniter

        while self._running:
            now = datetime.now()
            for task in list(self._tasks.values()):
                if not task.enabled:
                    continue
                try:
                    cron = croniter(task.cron_expr, now)
                    prev = cron.get_prev(datetime)
                    if task.last_run_at is None or task.last_run_at < prev.timestamp():
                        await self._trigger(task)
                except Exception:
                    logger.exception("Cron check failed for task %s", task.task_id)

            await asyncio.sleep(1)

    async def _trigger(self, task: ScheduledTask):
        logger.info("Triggering scheduled task: %s (%s)", task.description, task.task_id)
        trigger = TaskTrigger.from_task(task)
        await self._queue.put(trigger)
        task.last_run_at = time.time()
        self._save()
