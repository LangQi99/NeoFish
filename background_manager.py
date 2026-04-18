#!/usr/bin/env python3
"""
background_manager.py - Async background task execution for NeoFish agent.

Run commands in background using asyncio tasks. A notification queue is drained
before each agent step to deliver results.

Timeline:
    Agent ----[spawn A]----[spawn B]----[other work]----
                 |              |
                 v              v
              [A runs]      [B runs]        (parallel)
                 |              |
                 +-- notification queue --> [results injected]
"""

import os
import signal
import asyncio
import contextlib
import uuid
from typing import Optional, Dict, List, Any
from pathlib import Path
import time
from message_center import MessageCenter

# Default timeout for background tasks
BG_TASK_TIMEOUT = int(os.getenv("BG_TASK_TIMEOUT", "300"))  # 5 minutes default
WORKDIR = Path(os.getenv("WORKDIR", "./workspace")).resolve()


class BackgroundManager:
    """Manages background task execution using asyncio."""

    def __init__(self, workdir: Path = None, default_timeout: int = None):
        """
        Initialize background manager.

        Args:
            workdir: Working directory for commands
            default_timeout: Default timeout in seconds
        """
        self.workdir = (workdir or WORKDIR).resolve()
        self.default_timeout = default_timeout or BG_TASK_TIMEOUT
        self.tasks: Dict[str, Dict[str, Any]] = {}  # task_id -> task info
        self._notification_queue: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def run(
        self,
        command: str,
        timeout: int = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Start a background async task.

        Args:
            command: Shell command to execute
            timeout: Timeout in seconds (uses default if not specified)

        Returns:
            Task ID and status message
        """
        task_id = str(uuid.uuid4())[:8]
        use_timeout = timeout or self.default_timeout

        # Initialize task record
        self.tasks[task_id] = {
            "status": "running",
            "result": None,
            "command": command,
            "start_time": time.time(),
            "timeout": use_timeout,
            "session_id": session_id,
            "cancel_requested": False,
            "process": None,
            "runner_task": None,
        }

        # Create asyncio task
        runner_task = asyncio.create_task(
            self._execute(task_id, command, use_timeout, session_id)
        )
        self.tasks[task_id]["runner_task"] = runner_task

        return f"Background task {task_id} started: {command[:80]}"

    async def _terminate_process(self, process, grace_period: float = 3.0) -> None:
        """Terminate a background subprocess and its child processes if possible."""
        if process.returncode is not None:
            return

        try:
            if os.name == "posix":
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            return

        try:
            await asyncio.wait_for(process.wait(), timeout=grace_period)
            return
        except asyncio.TimeoutError:
            pass
        except ProcessLookupError:
            return

        try:
            if os.name == "posix":
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            return

        with contextlib.suppress(Exception):
            await process.wait()

    async def _execute(
        self,
        task_id: str,
        command: str,
        timeout: int,
        session_id: Optional[str] = None,
    ):
        """
        Execute a command in background (asyncio task target).

        Args:
            task_id: Task identifier
            command: Shell command
            timeout: Timeout in seconds
        """
        process = None
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workdir),
                start_new_session=(os.name == "posix"),
            )
            if task_id in self.tasks:
                self.tasks[task_id]["process"] = process

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                output = (stdout.decode() + stderr.decode()).strip()
                status = "completed"
            except asyncio.TimeoutError:
                if self.tasks.get(task_id, {}).get("cancel_requested"):
                    if process and process.returncode is None:
                        await self._terminate_process(process)
                    output = "Task cancelled by user"
                    status = "cancelled"
                else:
                    await self._terminate_process(process, grace_period=0.5)
                    output = f"Error: Timeout ({timeout}s)"
                    status = "timeout"
        except asyncio.CancelledError:
            if process and process.returncode is None:
                await self._terminate_process(process)
            output = "Task cancelled by user"
            status = "cancelled"

        except Exception as e:
            output = f"Error: {str(e)}"
            status = "error"

        # Update task record
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if task.get("cancel_requested"):
                status = "cancelled"
                output = output or "Task cancelled by user"
            task["status"] = status
            task["result"] = output or "(no output)"
            task["end_time"] = time.time()
            task["process"] = None

        # Add to notification queue
        async with self._lock:
            self._notification_queue.append({
                "task_id": task_id,
                "status": status,
                "command": command[:80],
                "result": (output or "(no output)")[:500],
                "elapsed": time.time() - self.tasks[task_id].get("start_time", time.time()),
                "session_id": session_id,
            })

        if session_id:
            center = MessageCenter(session_id)
            await center.publish(
                "background_task_update",
                {
                    "task_id": task_id,
                    "status": status,
                    "command": command[:80],
                    "result": (output or "(no output)")[:500],
                    "elapsed": time.time()
                    - self.tasks[task_id].get("start_time", time.time()),
                    "message": (
                        f"[bg:{task_id}] {status} ({time.time() - self.tasks[task_id].get('start_time', time.time()):.1f}s): "
                        f"{command[:50]}"
                    ),
                },
            )

    async def check(self, task_id: Optional[str] = None) -> str:
        """
        Check status of background tasks.

        Args:
            task_id: Specific task ID, or None to list all

        Returns:
            Task status information
        """
        if task_id:
            t = self.tasks.get(task_id)
            if not t:
                return f"Error: Unknown task {task_id}"

            elapsed = time.time() - t.get("start_time", time.time())
            result = t.get("result") or "(still running)"

            return (
                f"[{t['status']}] {t['command'][:60]}\n"
                f"Elapsed: {elapsed:.1f}s\n"
                f"Result: {result[:1000]}"
            )

        # List all tasks
        if not self.tasks:
            return "No background tasks."

        lines = []
        for tid, t in self.tasks.items():
            elapsed = time.time() - t.get("start_time", time.time())
            lines.append(f"{tid}: [{t['status']}] {t['command'][:50]} ({elapsed:.0f}s)")

        return "\n".join(lines)

    async def drain_notifications(
        self, session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Return and clear all pending completion notifications.

        Returns:
            List of notification dictionaries
        """
        async with self._lock:
            if session_id is None:
                notifs = list(self._notification_queue)
                self._notification_queue.clear()
                return notifs

            matching = []
            remaining = []
            for notif in self._notification_queue:
                if notif.get("session_id") == session_id:
                    matching.append(notif)
                else:
                    remaining.append(notif)
            self._notification_queue = remaining
            notifs = matching
        return notifs

    def format_notifications(self, notifs: List[Dict[str, Any]]) -> str:
        """
        Format notifications for injection into messages.

        Args:
            notifs: List of notification dicts

        Returns:
            Formatted string
        """
        if not notifs:
            return ""

        lines = []
        for n in notifs:
            lines.append(
                f"[bg:{n['task_id']}] {n['status']} ({n.get('elapsed', 0):.1f}s): "
                f"{n['command'][:50]}\n  Result: {n['result'][:200]}"
            )
        return "\n".join(lines)

    async def cancel(self, task_id: str) -> str:
        """
        Cancel a running background task.

        Args:
            task_id: Task ID to cancel

        Returns:
            Status message
        """
        t = self.tasks.get(task_id)
        if not t:
            return f"Error: Unknown task {task_id}"

        if t["status"] != "running":
            return f"Task {task_id} is not running (status: {t['status']})"

        t["cancel_requested"] = True

        process = t.get("process")
        runner_task = t.get("runner_task")

        if process and process.returncode is None:
            await self._terminate_process(process)
        elif runner_task and not runner_task.done():
            runner_task.cancel()

        if runner_task and not runner_task.done():
            with contextlib.suppress(asyncio.CancelledError):
                await runner_task

        t["status"] = "cancelled"
        t["result"] = "Task cancelled by user"
        t["end_time"] = time.time()

        return f"Task {task_id} cancelled."

    async def cancel_by_session(self, session_id: str) -> int:
        """Cancel all running background tasks for a specific session."""
        task_ids = [
            task_id
            for task_id, task in self.tasks.items()
            if task.get("session_id") == session_id and task.get("status") == "running"
        ]

        for task_id in task_ids:
            await self.cancel(task_id)

        return len(task_ids)

    async def cleanup_completed(self, max_age: int = 3600) -> int:
        """
        Remove old completed/timeout/error tasks.

        Args:
            max_age: Maximum age in seconds for completed tasks

        Returns:
            Number of tasks removed
        """
        now = time.time()
        to_remove = []

        for tid, t in self.tasks.items():
            if t["status"] in ("completed", "timeout", "error", "cancelled"):
                end_time = t.get("end_time", now)
                if now - end_time > max_age:
                    to_remove.append(tid)

        for tid in to_remove:
            del self.tasks[tid]

        return len(to_remove)


# Default instance
background_manager = BackgroundManager()
