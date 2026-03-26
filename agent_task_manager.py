"""
Agent task lifecycle management for NeoFish.

Manages agent tasks that can continue running even when WebSocket
disconnects, with support for cancellation and message buffering.
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, Dict, Any
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class AgentTask:
    session_id: str
    task: asyncio.Task
    status: TaskStatus = TaskStatus.RUNNING
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    message_buffer: Optional[deque] = None


class AgentTaskManager:
    """
    Manages agent tasks with lifecycle control and message buffering.

    Key features:
    - Tasks continue running when WebSocket disconnects
    - Messages are buffered and delivered on reconnection
    - Tasks can be cancelled via cancel_event
    - Task status tracking
    """

    def __init__(self, max_buffer_size: int = 100):
        self._tasks: Dict[str, AgentTask] = {}
        self.max_buffer_size = max_buffer_size

    def _create_task(self, session_id: str, task: Optional[asyncio.Task] = None, status: TaskStatus = TaskStatus.RUNNING, cancel_event: Optional[asyncio.Event] = None) -> AgentTask:
        return AgentTask(
            session_id=session_id,
            task=task,
            status=status,
            cancel_event=cancel_event or asyncio.Event(),
            message_buffer=deque(maxlen=self.max_buffer_size),
        )

    def has_running_task(self, session_id: str) -> bool:
        if session_id not in self._tasks:
            return False
        task = self._tasks[session_id]
        return task.status == TaskStatus.RUNNING and not task.task.done()

    def get_task_status(self, session_id: str) -> Optional[TaskStatus]:
        if session_id not in self._tasks:
            return None
        return self._tasks[session_id].status

    async def start_task(
        self, session_id: str, agent_fn: Callable, *args, **kwargs
    ) -> asyncio.Task:
        if self.has_running_task(session_id):
            raise RuntimeError(f"Task already running for session {session_id}")

        cancel_event = asyncio.Event()

        agent_task = self._create_task(session_id, None, TaskStatus.RUNNING, cancel_event)
        self._tasks[session_id] = agent_task

        async def wrapped_fn():
            task_ref = self._tasks[session_id]
            try:
                task_ref.status = TaskStatus.RUNNING
                await agent_fn(*args, cancel_event=cancel_event, **kwargs)
                task_ref.status = TaskStatus.COMPLETED
            except asyncio.CancelledError:
                task_ref.status = TaskStatus.CANCELLED
            except Exception as e:
                task_ref.status = TaskStatus.FAILED
                task_ref.error = str(e)
            finally:
                task_ref.completed_at = datetime.now()

        task = asyncio.create_task(wrapped_fn())
        self._tasks[session_id].task = task

        return task

    async def stop_task(self, session_id: str) -> bool:
        if session_id not in self._tasks:
            return False

        agent_task = self._tasks[session_id]

        if agent_task.status != TaskStatus.RUNNING:
            return False

        agent_task.cancel_event.set()

        if not agent_task.task.done():
            agent_task.task.cancel()
            try:
                await agent_task.task
            except asyncio.CancelledError:
                pass

        return True

    def buffer_message(self, session_id: str, message: Dict[str, Any]):
        if session_id not in self._tasks:
            self._tasks[session_id] = self._create_task(session_id, None, TaskStatus.PENDING)

        self._tasks[session_id].message_buffer.append(
            {
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def get_buffered_messages(self, session_id: str) -> list:
        if session_id not in self._tasks:
            return []

        messages = list(self._tasks[session_id].message_buffer)
        self._tasks[session_id].message_buffer.clear()
        return messages

    def cleanup_task(self, session_id: str):
        if session_id in self._tasks:
            del self._tasks[session_id]

    def cleanup_completed_tasks(self, max_age_seconds: int = 3600):
        now = datetime.now()
        to_cleanup = []

        for session_id, task in self._tasks.items():
            if task.status in (
                TaskStatus.COMPLETED,
                TaskStatus.CANCELLED,
                TaskStatus.FAILED,
            ):
                if task.completed_at:
                    age = (now - task.completed_at).total_seconds()
                    if age > max_age_seconds:
                        to_cleanup.append(session_id)

        for session_id in to_cleanup:
            del self._tasks[session_id]

    def get_all_running_sessions(self) -> list:
        return [
            sid
            for sid, task in self._tasks.items()
            if task.status == TaskStatus.RUNNING
        ]

    def get_stats(self) -> dict:
        status_counts = {status: 0 for status in TaskStatus}
        for task in self._tasks.values():
            status_counts[task.status] += 1

        return {
            "total_tasks": len(self._tasks),
            "status_counts": {s.value: c for s, c in status_counts.items()},
            "running_sessions": self.get_all_running_sessions(),
        }


task_manager = AgentTaskManager()
