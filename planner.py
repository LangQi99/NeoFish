#!/usr/bin/env python3
"""
planner.py - Dynamic plan management for NeoFish agent.

A single plan is stored as one JSON file (.plan/plan.json), surviving context
compression. A plan is an ordered list of steps that the agent can fully rewrite
at any time (dynamic re-planning).

Structure (.plan/plan.json):
    {
      "version": 1,
      "title": "...",
      "goal": "original user request",
      "steps": [
        {"id": 1, "content": "...", "status": "completed"},
        {"id": 2, "content": "...", "status": "in_progress"}
      ],
      "updated_at": "2026-06-07T10:00:00"
    }
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Default plan directory
PLAN_DIR = Path(os.getenv("PLAN_DIR", "./.plan")).resolve()

VALID_STATUS = ("pending", "in_progress", "completed", "skipped")

_STATUS_MARKERS = {
    "pending": "[ ]",
    "in_progress": "[>]",
    "completed": "[x]",
    "skipped": "[-]",
}


class PlanManager:
    """Manages a single, dynamically rewritable plan."""

    def __init__(self, plan_dir: Path = None):
        """
        Initialize plan manager.

        Args:
            plan_dir: Directory for plan storage. Defaults to PLAN_DIR env or ./.plan
        """
        self.dir = (plan_dir or PLAN_DIR).resolve()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "plan.json"

    def _empty(self) -> dict:
        return {"version": 1, "title": "", "goal": "", "steps": [], "updated_at": None}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return self._empty()

    def _save(self, plan: dict) -> dict:
        plan["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.path.write_text(
            json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return plan

    def write(
        self,
        steps: List[dict],
        goal: Optional[str] = None,
        title: Optional[str] = None,
    ) -> str:
        """
        Create or completely overwrite the plan's steps. This is the core of
        dynamic re-planning: pass the full ordered list of steps each time.

        Returns the rendered plan.
        """
        plan = self._load()
        if goal is not None:
            plan["goal"] = goal
        if title is not None:
            plan["title"] = title

        normalized = []
        for i, step in enumerate(steps, start=1):
            status = step.get("status", "pending")
            if status not in VALID_STATUS:
                status = "pending"
            normalized.append(
                {
                    "id": i,
                    "content": str(step.get("content", "")).strip(),
                    "status": status,
                }
            )
        plan["steps"] = normalized
        self._save(plan)
        return self.render()

    def update_step(
        self,
        step_id: int,
        status: Optional[str] = None,
        content: Optional[str] = None,
    ) -> str:
        """Update a single step's status or content. Returns the rendered plan."""
        plan = self._load()
        for step in plan["steps"]:
            if step["id"] == step_id:
                if status is not None:
                    if status not in VALID_STATUS:
                        return (
                            f"Error: invalid status '{status}'. "
                            f"Must be one of {VALID_STATUS}"
                        )
                    step["status"] = status
                if content is not None:
                    step["content"] = content.strip()
                self._save(plan)
                return self.render()
        return f"Error: step {step_id} not found"

    def set_goal(self, goal: str, title: Optional[str] = None) -> dict:
        """Set the plan goal/title without touching steps."""
        plan = self._load()
        plan["goal"] = goal
        if title is not None:
            plan["title"] = title
        return self._save(plan)

    def mark_all(self, status: str) -> dict:
        """Set every step to the given status (e.g. complete the whole plan)."""
        plan = self._load()
        for step in plan["steps"]:
            step["status"] = status
        return self._save(plan)

    def pause(self) -> dict:
        """Revert in_progress steps back to pending (on cancel/pause)."""
        plan = self._load()
        for step in plan["steps"]:
            if step["status"] == "in_progress":
                step["status"] = "pending"
        return self._save(plan)

    def render(self) -> str:
        """Render the plan as text for LLM / compaction context."""
        plan = self._load()
        if not plan["steps"] and not plan.get("goal"):
            return "No plan yet."
        lines = []
        if plan.get("goal"):
            lines.append(f"Goal: {plan['goal']}")
        for step in plan["steps"]:
            marker = _STATUS_MARKERS.get(step["status"], "[?]")
            lines.append(f"{marker} #{step['id']} {step['content']}")
        return "\n".join(lines)

    def get_plan(self) -> dict:
        """Return the full plan as structured data."""
        return self._load()

    def clear(self) -> str:
        """Reset the plan to empty."""
        self._save(self._empty())
        return "Plan cleared."


# Default instance
plan_manager = PlanManager()
