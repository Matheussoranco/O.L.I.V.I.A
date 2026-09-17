"""Tolerant structured-output helpers — LLM text → JSON, never raising.

LLMs wrap JSON in prose, code fences, or ``<think>`` blocks; these helpers dig
the payload out.  Every consumer must handle ``None`` (parse failure or LLM
unavailable) by falling back to its deterministic path.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from olivia.llm.client import LLMClient

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _balanced_spans(text: str) -> list[str]:
    """All balanced ``{…}`` / ``[…]`` spans in *text* (string-aware)."""
    spans: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] not in "{[":
            i += 1
            continue
        open_c, close_c = (("{", "}")) if text[i] == "{" else (("[", "]"))
        depth = 0
        in_str = False
        esc = False
        for j in range(i, n):
            ch = text[j]
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
            elif ch == open_c:
                depth += 1
            elif ch == close_c:
                depth -= 1
                if depth == 0:
                    spans.append(text[i : j + 1])
                    break
        i = (j + 1) if depth == 0 else (i + 1)
    return spans


def extract_json(text: str, expected_key: str | None = None) -> Any | None:
    """Best-effort: return the JSON payload in free-form text.

    ``expected_key`` (e.g. ``"answer"``, ``"hypotheses"``): when given, the
    LAST span containing that key wins — LLMs often emit a draft object
    then a corrected one, and the first-valid heuristic shipped the draft.
    Without ``expected_key`` the LAST parseable span wins for the same
    reason (a trailing corrected object beats an early sketch).  Returns
    ``None`` when nothing parses.
    """
    if not text:
        return None
    text = _THINK_RE.sub("", text)
    candidates = [*_FENCE_RE.findall(text), text]
    found: list[Any] = []
    for candidate in candidates:
        candidate = candidate.strip()
        # Try verbatim first, then every balanced span (not just outermost).
        try:
            found.append(json.loads(candidate))
            continue
        except json.JSONDecodeError:
            pass
        for span in _balanced_spans(candidate):
            try:
                found.append(json.loads(span))
            except json.JSONDecodeError:
                continue
    if not found:
        return None
    if expected_key:
        for payload in reversed(found):
            if isinstance(payload, dict) and expected_key in payload:
                return payload
    return found[-1]


def ask_json(
    client: LLMClient,
    prompt: str,
    system: str = "",
    max_tokens: int | None = None,
) -> Any | None:
    """One-shot completion that must yield JSON; ``None`` when it can't."""
    if not client.available:
        return None
    text = client.ask(
        prompt + "\n\nRespond with ONLY valid JSON — no prose, no code fences.",
        system=system,
        max_tokens=max_tokens,
    )
    parsed = extract_json(text)
    if parsed is None and text:
        logger.debug("ask_json: unparseable response %.200s", text)
    return parsed
