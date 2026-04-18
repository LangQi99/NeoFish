"""
tool_registry.py - Runtime tool handler registry for NeoFish agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass
class ToolExecutionResult:
    output: str
    finished: bool = False
    manual_compact: bool = False
    compact_focus: str | None = None


ToolHandler = Callable[[dict], Awaitable[ToolExecutionResult]]


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, name: str, handler: ToolHandler) -> None:
        self._handlers[name] = handler

    async def execute(self, name: str, args: dict) -> ToolExecutionResult:
        handler = self._handlers.get(name)
        if handler is None:
            return ToolExecutionResult(output=f"Unknown tool: {name}")
        return await handler(args)

