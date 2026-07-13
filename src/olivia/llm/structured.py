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


def extract_json(text: str) -> Any | None:
    """Best-effort: return the first JSON value found in free-form text."""
    if not text:
        return None
    text = _THINK_RE.sub("", text)
    candidates = [*_FENCE_RE.findall(text), text]
    for candidate in candidates:
        candidate = candidate.strip()
        # Try verbatim first, then the outermost {...} / [...] span.
        for start_char, end_char in (("", ""), ("{", "}"), ("[", "]")):
            if start_char:
                start = candidate.find(start_char)
                end = candidate.rfind(end_char)
                if start == -1 or end <= start:
                    continue
                snippet = candidate[start : end + 1]
            else:
                snippet = candidate
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                continue
    return None


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
