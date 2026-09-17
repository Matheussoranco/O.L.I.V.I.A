"""Hermes-style tool calling — the Nous Research function-calling protocol.

Instead of relying on a provider's native tool-use API, tools are described as
JSON Schemas inside a ``<tools>`` block of the system prompt and the model
emits calls as::

    <tool_call>
    {"name": "literature_search", "arguments": {"query": "spaced repetition"}}
    </tool_call>

Results are fed back inside ``<tool_response>`` blocks.  This makes the agent
loop work identically on Claude, on local Ollama models with no tool-use
training, and on anything in between — the same portability that makes the
Hermes agent stack model-agnostic.  ``<think>...</think>`` blocks are treated
as reasoning traces and stripped from user-facing answers.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from olivia.llm.client import LLMClient
    from olivia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)

HERMES_TOOL_PROMPT = """\
You are a function-calling AI. You may call tools to help answer the task.
Available tools are listed inside <tools></tools> as JSON Schemas:

<tools>
{tool_schemas}
</tools>

To call a tool, emit exactly this block (one per call, valid JSON inside):
<tool_call>
{{"name": "<tool-name>", "arguments": {{<args>}}}}
</tool_call>

Tool results will be returned to you inside <tool_response></tool_response>
blocks. When you have enough information, answer directly WITHOUT any
<tool_call> block. You may reason privately inside <think></think> blocks.
"""


@dataclass
class ToolCall:
    """One parsed tool invocation."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Outcome of a HermesAgent run."""

    answer: str = ""
    reasoning: str = ""
    turns: int = 0
    tool_calls: list[ToolCall] = field(default_factory=list)
    transcript: list[dict[str, str]] = field(default_factory=list)
    error: str = ""


def _extract_tool_json_blocks(text: str) -> list[str]:
    """Raw JSON payloads inside ``<tool_call>…</tool_call>`` blocks.

    Balanced-brace parser (brace-depth stack), NOT a non-greedy regex:
    ``\\{.*?\\}`` stops at the first ``}`` so nested ``arguments`` objects
    (``{"arguments": {"q": {"a": 1}}}``) were truncated to invalid JSON.
    This scans from each ``<tool_call>`` to its closing tag, then takes the
    first balanced ``{…}`` span (respecting strings/escapes).
    """
    out: list[str] = []
    pos = 0
    while True:
        start_tag = text.find("<tool_call>", pos)
        if start_tag == -1:
            break
        end_tag = text.find("</tool_call>", start_tag)
        if end_tag == -1:
            break
        inner = text[start_tag + len("<tool_call>") : end_tag]
        payload = _balanced_json_span(inner)
        if payload is not None:
            out.append(payload)
        pos = end_tag + len("</tool_call>")
    return out


def _balanced_json_span(s: str) -> str | None:
    """First balanced ``{…}`` span in *s*, respecting JSON strings/escapes."""
    i = s.find("{")
    if i == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for j in range(i, len(s)):
        ch = s[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[i : j + 1]
    return None  # unbalanced — caller skips


def _strip_tool_call_blocks(text: str) -> str:
    """Remove ``<tool_call>…</tool_call>`` spans (balanced-tag strip)."""
    out: list[str] = []
    pos = 0
    while True:
        start_tag = text.find("<tool_call>", pos)
        if start_tag == -1:
            out.append(text[pos:])
            break
        end_tag = text.find("</tool_call>", start_tag)
        if end_tag == -1:
            out.append(text[pos:])
            break
        out.append(text[pos:start_tag])
        pos = end_tag + len("</tool_call>")
    return "".join(out)


def render_tool_prompt(tools: list[Any]) -> str:
    """Render the Hermes system-prompt section for a list of Tools."""
    schemas = [
        {"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools
    ]
    return HERMES_TOOL_PROMPT.format(tool_schemas=json.dumps(schemas, indent=2))


def parse_tool_calls(text: str) -> list[ToolCall]:
    """Extract every ``<tool_call>`` block; tolerate malformed JSON."""
    calls: list[ToolCall] = []
    for raw in _extract_tool_json_blocks(text):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Skipping malformed tool_call: %.120s", raw)
            continue
        name = payload.get("name")
        if not name:
            continue
        args = payload.get("arguments") or {}
        if not isinstance(args, dict):
            args = {"value": args}
        calls.append(ToolCall(name=str(name), arguments=args))
    return calls


def strip_think(text: str) -> tuple[str, str]:
    """Split text into (visible, reasoning-trace) parts."""
    thoughts = "\n".join(m.group(1).strip() for m in _THINK_RE.finditer(text))
    visible = _THINK_RE.sub("", text)
    visible = _strip_tool_call_blocks(visible).strip()
    return visible, thoughts


def format_tool_response(name: str, result: Any) -> str:
    """Wrap a tool result for feeding back to the model."""
    if not isinstance(result, str):
        try:
            result = json.dumps(result, ensure_ascii=False, default=str)
        except TypeError:
            result = str(result)
    if len(result) > 8000:
        result = result[:8000] + "\n...[truncated]"
    payload = f'{{"name": "{name}", "content": {json.dumps(result)}}}'
    return f"<tool_response>\n{payload}\n</tool_response>"


class HermesAgent:
    """A model-agnostic agent loop: complete → parse calls → execute → repeat."""

    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry,
        system_prompt: str = "",
        max_turns: int = 8,
        allow_risky_tools: bool = False,
    ) -> None:
        self.client = client
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.allow_risky_tools = allow_risky_tools

    def run(self, task: str, context: str = "") -> AgentResult:
        if not self.client.available:
            return AgentResult(error="llm unavailable")

        system = self.system_prompt + "\n\n" + render_tool_prompt(self.registry.list())
        user = f"{task}\n\nContext:\n{context}" if context else task
        messages: list[dict[str, str]] = [{"role": "user", "content": user}]
        result = AgentResult()

        for turn in range(1, self.max_turns + 1):
            result.turns = turn
            response = self.client.complete(messages, system=system)
            if response.error:
                result.error = response.error
                break
            messages.append({"role": "assistant", "content": response.text})
            calls = parse_tool_calls(response.text)
            visible, thoughts = strip_think(response.text)
            if thoughts:
                result.reasoning += thoughts + "\n"
            if not calls:
                result.answer = visible
                break
            result.tool_calls.extend(calls)
            responses = [
                format_tool_response(
                    c.name,
                    self.registry.execute(c.name, c.arguments, allow_risky=self.allow_risky_tools),
                )
                for c in calls
            ]
            messages.append({"role": "user", "content": "\n".join(responses)})
        else:
            result.error = "max turns exceeded"

        result.transcript = messages
        return result
