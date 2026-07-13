"""Tool registry — JSON-Schema-described callables, Hermes-exportable.

Modules register their tools into :data:`default_registry` via a module-level
``register_tools(registry)`` function so imports stay side-effect-free until
the CLI / MCP server / HermesAgent explicitly wires everything together.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Tool:
    """A named callable with a JSON-Schema signature."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    fn: Callable[..., Any] | None = None
    risk: int = 1
    """1 = read-only, 3 = writes local state, 5 = executes code / network side-effects."""


class ToolRegistry:
    """Name → Tool mapping with safe execution."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        return tool

    def tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any] | None = None,
        risk: int = 1,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator form: ``@registry.tool("web_search", "...", {...})``."""

        def wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.register(
                Tool(
                    name=name,
                    description=description,
                    parameters=parameters or {"type": "object", "properties": {}},
                    fn=fn,
                    risk=risk,
                )
            )
            return fn

        return wrap

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return sorted(self._tools)

    def execute(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Invoke a tool; return an error string rather than raising."""
        tool = self._tools.get(name)
        if tool is None or tool.fn is None:
            return f"error: unknown tool '{name}'"
        try:
            return tool.fn(**(arguments or {}))
        except TypeError as exc:
            return f"error: bad arguments for '{name}': {exc}"
        except Exception as exc:
            logger.warning("Tool %s failed: %s", name, exc)
            return f"error: {exc}"


default_registry = ToolRegistry()
