"""Hybrid router — symbolic can-handle scores blended with learned win-rates.

``final = 0.7 * symbolic_score + 0.3 * historical_win_rate`` (I.S.A.A.C.'s
HybridRouter recipe): heuristics dominate cold-start, experience dominates as
the MetaLearner ledger grows.  Cascade mode walks the ranking until an expert
clears the confidence threshold.
"""

from __future__ import annotations

import logging
import time

from olivia.experts.base import Expert, ExpertAnswer
from olivia.experts.code_expert import CodeExpert
from olivia.experts.general_expert import GeneralExpert
from olivia.experts.literature_expert import LiteratureExpert
from olivia.experts.math_expert import MathExpert
from olivia.experts.science_expert import ScienceExpert
from olivia.experts.stats_expert import StatsExpert
from olivia.llm.client import LLMClient

logger = logging.getLogger(__name__)

_SYMBOLIC_WEIGHT = 0.7
_HISTORY_WEIGHT = 0.3
_MIN_SCORE = 0.05

_experts: list[Expert] | None = None


def get_experts() -> list[Expert]:
    """The expert singletons, specialists before the general catch-all."""
    global _experts
    if _experts is None:
        _experts = [
            MathExpert(),
            StatsExpert(),
            ScienceExpert(),
            CodeExpert(),
            LiteratureExpert(),
            GeneralExpert(),
        ]
    return _experts


def _win_rate(expert_name: str) -> float | None:
    """Historical win-rate for the 'ask' task, or None when unavailable."""
    try:
        from olivia.meta.learner import get_meta_learner

        return get_meta_learner().win_rate("ask", expert_name)
    except Exception as exc:
        logger.debug("win_rate lookup failed: %s", exc)
        return None


def route(question: str) -> list[tuple[Expert, float]]:
    """Rank experts for a question, best first."""
    ranked = []
    for expert in get_experts():
        score = expert.score(question)
        history = _win_rate(expert.name)
        blended = (
            _SYMBOLIC_WEIGHT * score + _HISTORY_WEIGHT * history if history is not None else score
        )
        ranked.append((expert, blended))
    ranked.sort(key=lambda pair: pair[1], reverse=True)
    return ranked


def _record(expert: Expert, success: bool, duration_s: float) -> None:
    try:
        from olivia.meta.learner import get_meta_learner

        get_meta_learner().record("ask", expert.name, success, duration_s)
    except Exception as exc:
        logger.debug("meta record failed: %s", exc)


def answer(
    question: str,
    client: LLMClient | None = None,
    mode: str = "cascade",
    threshold: float = 0.35,
) -> ExpertAnswer:
    """Answer via the expert mixture.

    ``single`` runs only the top-routed expert; ``cascade`` (default) walks
    the ranking and accepts the first answer whose confidence clears the
    threshold, otherwise returning the best attempt seen.
    """
    ranked = route(question)
    if mode == "single":
        ranked = ranked[:1]

    best: ExpertAnswer | None = None
    for expert, score in ranked:
        if score < _MIN_SCORE:
            continue
        started = time.perf_counter()
        attempt = expert.answer(question, client)
        _record(expert, attempt.confidence >= threshold, time.perf_counter() - started)
        if best is None or attempt.confidence > best.confidence:
            best = attempt
        if attempt.confidence >= threshold:
            return attempt
    return best or ExpertAnswer(expert="none", answer="No expert could attempt this question.")
