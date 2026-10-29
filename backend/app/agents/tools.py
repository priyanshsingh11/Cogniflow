"""Tool abstraction the agent runtime calls. No tools exist yet: RAG search
(phase 3) and MCP tools (phase 4) will register themselves here."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

ToolFn = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass
class Tool:
    name: str
    description: str
    fn: ToolFn
    # Minimal schema: argument name -> short description. All are required.
    arguments: dict[str, str] = field(default_factory=dict)
    # Sensitive tools need human approval (phase 6). Until that exists the
    # runtime refuses to run them.
    requires_approval: bool = False


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools = {t.name: t for t in tools or []}

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __bool__(self) -> bool:
        return bool(self._tools)

    def describe(self) -> str:
        lines = []
        for t in self._tools.values():
            args = ", ".join(f"{k} ({v})" for k, v in t.arguments.items()) or "none"
            lines.append(f"- {t.name}: {t.description} Arguments: {args}")
        return "\n".join(lines)
