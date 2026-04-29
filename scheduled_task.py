"""
scheduled_task.py — Data classes for the NeoFish scheduled task system.

All inter-component data passing uses typed dataclasses instead of
naked dictionaries, giving IDE autocompletion, runtime type safety,
and a single source of truth for field definitions.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


# ── Task Configuration (persisted to JSON) ─────────────────────────────

@dataclass
class ScheduledTask:
    """A user-created recurring task configuration.

    Persisted to ``data/scheduled_tasks.json``.  Created by the
    ``schedule_task`` agent tool and consumed by SchedulerService.
    """

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
    last_status: Optional[str] = None  # "success" | "failed" | "error"

    @classmethod
    def new(
        cls,
        cron_expr: str,
        description: str,
        prompt: str,
        source_session_id: str,
        source_chat_id: str,
        source_platform: str,
        debug: bool = False,
    ) -> "ScheduledTask":
        return cls(
            task_id=str(uuid.uuid4()),
            cron_expr=cron_expr,
            description=description,
            prompt=prompt,
            source_session_id=source_session_id,
            source_chat_id=source_chat_id,
            source_platform=source_platform,
            debug=debug,
        )


# ── Queue Message (SchedulerService → BotSession) ──────────────────────

@dataclass
class TaskTrigger:
    """A triggered task injected into the BotSession queue.

    This replaces the ad-hoc dict that was previously constructed in
    ``SchedulerService._trigger()``.  Every field is mandatory so there
    are no ``.get()`` calls with fallback defaults on the receiving side.
    """

    task_id: str
    description: str
    prompt: str
    source_session_id: str
    source_chat_id: str
    source_platform: str
    debug: bool = False

    @classmethod
    def from_task(cls, task: ScheduledTask) -> "TaskTrigger":
        """Create a trigger from a ScheduledTask configuration."""
        return cls(
            task_id=task.task_id,
            description=task.description,
            prompt=task.prompt,
            source_session_id=task.source_session_id,
            source_chat_id=task.source_chat_id,
            source_platform=task.source_platform,
            debug=task.debug,
        )


# ── Execution Result (BotSession → callback) ───────────────────────────

@dataclass
class BotTaskResult:
    """The outcome of a single scheduled task execution."""

    task_id: str
    description: str
    status: str  # "success" | "failed" | "error"
    summary: str
    files: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def is_success(self) -> bool:
        return self.status == "success"


# ── Source Context (platform adapter → agent tools) ────────────────────

@dataclass
class SourceMeta:
    """Identifies the originating conversation for tool context.

    Passed through ``run_agent_loop`` → ``_create_tool_registry`` so
    that ``schedule_task`` / ``list_scheduled_tasks`` /
    ``cancel_scheduled_task`` handlers know which session owns the task.
    """

    session_id: str
    chat_id: str
    platform: str
