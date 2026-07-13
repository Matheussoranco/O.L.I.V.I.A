"""Expert protocol — cheap symbolic routing scores, honest confidences.

``score()`` must be pure keyword/regex heuristics (no LLM, no network) so the
router can rank every expert in microseconds; ``answer()`` may use symbolic
engines, tools, or an LLM, and reports a confidence the router can act on.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from olivia.llm.client import LLMClient


@dataclass
class ExpertAnswer:
    """One expert's attempt at a question."""

    expert: str
    answer: str = ""
    confidence: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


class Expert(abc.ABC):
    """A specialist with a can-handle estimate and an answer path."""

    name: str = "base"
    description: str = ""

    @abc.abstractmethod
    def score(self, question: str) -> float:
        """0..1 symbolic estimate of fitness for this question. No LLM, no I/O."""

    @abc.abstractmethod
    def answer(self, question: str, client: LLMClient | None = None) -> ExpertAnswer:
        """Attempt the question; confidence 0.0 means 'could not help'."""


def keyword_score(
    question: str,
    keywords: list[str],
    base: float = 0.0,
    per_hit: float = 0.25,
    cap: float = 0.95,
) -> float:
    """Simple additive keyword heuristic shared by the concrete experts."""
    text = question.lower()
    hits = sum(1 for kw in keywords if kw in text)
    return min(base + per_hit * hits, cap)
