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

    def execute(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        allow_risky: bool = False,
    ) -> Any:
        """Invoke a tool; risky tools require an explicit caller opt-in."""
        tool = self._tools.get(name)
        if tool is None or tool.fn is None:
            return f"error: unknown tool '{name}'"
        if tool.risk >= 5 and not allow_risky:
            return f"error: tool '{name}' requires explicit allow_risky=True"
        validation_error = _validate_arguments(tool.parameters, arguments or {})
        if validation_error:
            return f"error: {validation_error}"
        try:
            return tool.fn(**(arguments or {}))
        except TypeError as exc:
            return f"error: bad arguments for '{name}': {exc}"
        except Exception as exc:
            logger.warning("Tool %s failed: %s", name, exc)
            return f"error: {exc}"


default_registry = ToolRegistry()


def _validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    """Validate the bounded JSON-schema subset used by local tools."""
    properties = schema.get("properties", {})
    missing = [key for key in schema.get("required", []) if key not in arguments]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}"
    unknown = [key for key in arguments if key not in properties]
    if unknown:
        return f"unknown argument(s): {', '.join(unknown)}"
    for name, value in arguments.items():
        rule = properties[name]
        kind = rule.get("type")
        valid = {
            "string": isinstance(value, str),
            "boolean": isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "array": isinstance(value, list),
            "object": isinstance(value, dict),
        }.get(kind, True)
        if not valid:
            return f"argument '{name}' must be {kind}"
        if "enum" in rule and value not in rule["enum"]:
            return f"argument '{name}' must be one of {rule['enum']}"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in rule and value < rule["minimum"]:
                return f"argument '{name}' is below the minimum"
            if "maximum" in rule and value > rule["maximum"]:
                return f"argument '{name}' exceeds the maximum"
        if isinstance(value, list) and isinstance(rule.get("items"), dict):
            for index, item in enumerate(value):
                item_rule = rule["items"]
                item_kind = item_rule.get("type")
                if item_kind == "string" and not isinstance(item, str):
                    return f"argument '{name}[{index}]' must be string"
    return None
