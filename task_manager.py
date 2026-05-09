#!/usr/bin/env python3
"""
task_manager.py - Persistent task management for NeoFish agent.

Tasks are stored as JSON files in .tasks/ directory, surviving context compression.
Each task has a dependency graph (blockedBy/blocks) for task ordering.

Structure:
    .tasks/
      task_1.json  {"id":1, "subject":"...", "status":"completed", ...}
      task_2.json  {"id":2, "blockedBy":[1], "status":"pending", ...}
"""

import json
import os
from pathlib import Path
from typing import Optional, List

# Default tasks directory
TASKS_DIR = Path(os.getenv("TASKS_DIR", "./.tasks")).resolve()


class TaskManager:
    """Manages persistent tasks with dependency tracking."""

    def __init__(self, tasks_dir: Path = None):
        """
        Initialize task manager.

        Args:
            tasks_dir: Directory for task storage. Defaults to TASKS_DIR env or ./.tasks
        """
        self.dir = (tasks_dir or TASKS_DIR).resolve()
        self.dir.mkdir(parents=True, exist_ok=True)
        self._next_id = self._max_id() + 1

    def _max_id(self) -> int:
        """Get the highest task ID from existing files."""
        ids = []
        for f in self.dir.glob("task_*.json"):
            try:
                task_id = int(f.stem.split("_")[1])
                ids.append(task_id)
            except (IndexError, ValueError):
                continue
        return max(ids) if ids else 0

    def _load(self, task_id: int) -> dict:
        """Load a task from file."""
        path = self.dir / f"task_{task_id}.json"
        if not path.exists():
            raise ValueError(f"Task {task_id} not found")
        return json.loads(path.read_text(encoding='utf-8'))

    def _save(self, task: dict):
        """Save a task to file."""
        path = self.dir / f"task_{task['id']}.json"
        path.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding='utf-8')

    def create(self, subject: str, description: str = "") -> str:
        """
        Create a new task.

        Args:
            subject: Brief task title
            description: Detailed task description

        Returns:
            JSON string of created task
        """
        task = {
            "id": self._next_id,
            "subject": subject,
            "description": description,
            "status": "pending",
            "blockedBy": [],
            "blocks": [],
            "owner": "",
            "metadata": {}
        }
        self._save(task)
        self._next_id += 1
        return json.dumps(task, indent=2, ensure_ascii=False)

    def get(self, task_id: int) -> str:
        """
        Get full details of a task.

        Args:
            task_id: Task ID

        Returns:
            JSON string of task details
        """
        try:
            task = self._load(task_id)
            return json.dumps(task, indent=2, ensure_ascii=False)
        except ValueError as e:
            return f"Error: {str(e)}"

    def update(
        self,
        task_id: int,
        status: Optional[str] = None,
        add_blocked_by: Optional[List[int]] = None,
        add_blocks: Optional[List[int]] = None,
        owner: Optional[str] = None
    ) -> str:
        """
        Update a task's status or dependencies.

        Args:
            task_id: Task ID
            status: New status (pending, planning, awaiting_approval, in_progress, completed)
            add_blocked_by: Task IDs this task depends on
            add_blocks: Task IDs that depend on this task
            owner: Owner identifier

        Returns:
            JSON string of updated task
        """
        try:
            task = self._load(task_id)

            # Update status
            if status:
                valid_statuses = ("pending", "planning", "awaiting_approval", "in_progress", "completed")
                if status not in valid_statuses:
                    return f"Error: Invalid status '{status}'. Must be one of {valid_statuses}"
                task["status"] = status

                # When completed, clear this task from other tasks' blockedBy
                if status == "completed":
                    self._clear_dependency(task_id)

            # Add blockedBy dependencies
            if add_blocked_by:
                task["blockedBy"] = list(set(task["blockedBy"] + add_blocked_by))

            # Add blocks dependencies (and update reverse links)
            if add_blocks:
                task["blocks"] = list(set(task["blocks"] + add_blocks))
                for blocked_id in add_blocks:
                    try:
                        blocked = self._load(blocked_id)
                        if task_id not in blocked["blockedBy"]:
                            blocked["blockedBy"].append(task_id)
                            self._save(blocked)
                    except ValueError:
                        pass  # Skip non-existent tasks

            # Update owner
            if owner is not None:
                task["owner"] = owner

            self._save(task)
            return json.dumps(task, indent=2, ensure_ascii=False)

        except ValueError as e:
            return f"Error: {str(e)}"

    def _clear_dependency(self, completed_id: int):
        """Remove completed_id from all other tasks' blockedBy lists."""
        for f in self.dir.glob("task_*.json"):
            try:
                task = json.loads(f.read_text(encoding='utf-8'))
                if completed_id in task.get("blockedBy", []):
                    task["blockedBy"].remove(completed_id)
                    self._save(task)
            except (json.JSONDecodeError, KeyError):
                continue

    def list_all(self) -> str:
        """
        List all tasks with status summary.

        Returns:
            Formatted task list
        """
        tasks = []
        for f in sorted(self.dir.glob("task_*.json")):
            try:
                tasks.append(json.loads(f.read_text(encoding='utf-8')))
            except json.JSONDecodeError:
                continue

        if not tasks:
            return "No tasks found."

        lines = []
        status_markers = {
            "pending": "[ ]",
            "planning": "[plan]",
            "awaiting_approval": "[wait]",
            "in_progress": "[>]",
            "completed": "[x]"
        }

        for t in tasks:
            marker = status_markers.get(t.get("status", "pending"), "[?]")
            blocked_by = t.get("blockedBy", [])
            blocked_str = f" (blocked by: {blocked_by})" if blocked_by else ""
            owner_str = f" @{t.get('owner')}" if t.get("owner") else ""
            lines.append(f"{marker} #{t['id']}: {t['subject']}{blocked_str}{owner_str}")

        return "\n".join(lines)

    def list_tasks(self) -> list[dict]:
        """Return all tasks as structured data sorted by numeric task ID."""
        tasks: list[dict] = []

        def _task_sort_key(path: Path) -> int:
            try:
                return int(path.stem.split("_")[1])
            except (IndexError, ValueError):
                return 0

        for f in sorted(self.dir.glob("task_*.json"), key=_task_sort_key):
            try:
                tasks.append(json.loads(f.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue

        return tasks

    def delete(self, task_id: int) -> str:
        """
        Delete a task.

        Args:
            task_id: Task ID to delete

        Returns:
            Success message or error
        """
        path = self.dir / f"task_{task_id}.json"
        if not path.exists():
            return f"Error: Task {task_id} not found"

        # Remove this task from other tasks' dependencies
        try:
            task = self._load(task_id)
            # Remove from blockedBy of tasks that this task blocks
            for blocked_id in task.get("blocks", []):
                try:
                    blocked = self._load(blocked_id)
                    if task_id in blocked.get("blockedBy", []):
                        blocked["blockedBy"].remove(task_id)
                        self._save(blocked)
                except ValueError:
                    pass
        except ValueError:
            pass

        path.unlink()
        return f"Task {task_id} deleted."

    def clear_all(self) -> str:
        """Delete all tasks."""
        count = 0
        for f in self.dir.glob("task_*.json"):
            f.unlink()
            count += 1
        return f"Cleared {count} tasks."


# Default instance
task_manager = TaskManager()
