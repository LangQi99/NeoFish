"""
memory/session_memory.py - Structured session memory for agent loops.

Replaces the need for the agent to track "where am I in the task" by
maintaining a real-time structured snapshot across the session.

Section limits (per Claude Code's design):
    - Each section: 2000 tokens
    - Total: 12000 tokens
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


SECTION_TEMPLATE = """## Current State
...

## Task Specification
...

## Important Files
...

## Workflow
...

## Errors & Corrections
...

## Learnings
...

## Pending Tasks
...
"""

SECTION_KEYS = [
    "current_state",
    "task_spec",
    "important_files",
    "workflow",
    "errors_corrections",
    "learnings",
    "pending_tasks",
]

SECTION_SUMMARIES = {
    "current_state": "What is currently being done, progress status",
    "task_spec": "What the user asked to build, core requirements",
    "important_files": "Key files and their purposes / modification history",
    "workflow": "Common build, test, deploy commands",
    "errors_corrections": "Errors encountered and how they were fixed",
    "learnings": "What worked, what didn't",
    "pending_tasks": "Explicit pending tasks",
}

SECTION_MAX_CHARS = {
    "current_state": 1500,
    "task_spec": 1500,
    "important_files": 2000,
    "workflow": 1500,
    "errors_corrections": 2000,
    "learnings": 1500,
    "pending_tasks": 2000,
}


@dataclass
class MemoryEntry:
    content: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"content": self.content, "timestamp": self.timestamp}

    @staticmethod
    def from_dict(d: dict) -> MemoryEntry:
        return MemoryEntry(content=d["content"], timestamp=d.get("timestamp", 0))


class SessionMemory:
    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id
        self._sections: dict[str, list[MemoryEntry]] = {k: [] for k in SECTION_KEYS}

    # ── Public API ──────────────────────────────────────────────────────────────

    def update(self, section: str, content: str) -> None:
        if section not in SECTION_KEYS:
            raise ValueError(f"Unknown section: {section}. Must be one of {SECTION_KEYS}")
        max_chars = SECTION_MAX_CHARS.get(section, 2000)
        if len(content) > max_chars:
            content = content[:max_chars]
        self._sections[section].append(MemoryEntry(content=content))

    def append(self, section: str, line: str) -> None:
        existing = self.get(section)
        if existing.strip():
            new_content = existing + "\n" + line
        else:
            new_content = line
        self.update(section, new_content)

    def get(self, section: str) -> str:
        if section not in SECTION_KEYS:
            raise ValueError(f"Unknown section: {section}")
        entries = self._sections.get(section, [])
        if not entries:
            return ""
        return entries[-1].content

    def get_all(self) -> str:
        parts = [f"# Session Memory\n"]
        for key in SECTION_KEYS:
            content = self.get(key)
            summary = SECTION_SUMMARIES.get(key, "")
            if content:
                parts.append(f"## {key.replace('_', ' ').title()} [{summary}]\n{content}\n")
            else:
                parts.append(f"## {key.replace('_', ' ').title()} [{summary}]\n...\n")
        return "\n".join(parts)

    def get_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "sections": {k: [e.to_dict() for e in v] for k, v in self._sections.items()},
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> SessionMemory:
        if data is None:
            return cls()
        instance = cls(session_id=data.get("session_id"))
        raw_sections = data.get("sections", {})
        for key in SECTION_KEYS:
            entries_data = raw_sections.get(key, [])
            instance._sections[key] = [MemoryEntry.from_dict(e) for e in entries_data]
        return instance

    def to_compact_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "sections": {k: self.get(k) for k in SECTION_KEYS},
        }

    @classmethod
    def from_compact_dict(cls, data: dict | None) -> SessionMemory:
        if data is None:
            return cls()
        instance = cls(session_id=data.get("session_id"))
        raw_sections = data.get("sections", {})
        for key in SECTION_KEYS:
            content = raw_sections.get(key, "") or ""
            if content:
                instance._sections[key] = [MemoryEntry(content=content)]
        return instance

    def is_empty(self) -> bool:
        return all(not self.get(k) for k in SECTION_KEYS)

    def clear(self) -> None:
        self._sections = {k: [] for k in SECTION_KEYS}
