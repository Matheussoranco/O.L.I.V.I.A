"""OliviaState — the data contract circulating through the cognitive graph.

Messages are plain ``{"role": ..., "content": ...}`` dicts so the core has no
langchain dependency; the same state dict drives both the LangGraph build and
the sequential fallback pipeline in :mod:`olivia.core.graph`.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from olivia.core.records import (
    AnalysisResult,
    DiscoveryReport,
    ExperimentPlan,
    Flashcard,
    Hypothesis,
    Paper,
    QuizQuestion,
    StudyPlan,
)

# ---------------------------------------------------------------------------
# Reducers (typing metadata LangGraph understands; harmless without it)
# ---------------------------------------------------------------------------


def _append(left: list[Any], right: list[Any]) -> list[Any]:
    """Append-only merge."""
    return list(left) + list(right)


def _replace(left: Any, right: Any) -> Any:
    """Latest-wins merge."""
    return right


Mode = Literal["ask", "research", "study"]


class OliviaState(TypedDict, total=False):
    """Root state schema for the O.L.I.V.I.A. cognitive graph."""

    messages: Annotated[list[dict[str, str]], _append]
    question: Annotated[str, _replace]
    mode: Annotated[Mode, _replace]
    phase: Annotated[str, _replace]
    iteration: Annotated[int, _replace]
    errors: Annotated[list[str], _append]

    # ── Research cycle ──────────────────────────────────────────────────────
    papers: Annotated[list[Paper], _append]
    hypotheses: Annotated[list[Hypothesis], _append]
    experiments: Annotated[list[ExperimentPlan], _append]
    analyses: Annotated[list[AnalysisResult], _append]
    critique: Annotated[str, _replace]
    needs_revision: Annotated[bool, _replace]
    report: Annotated[DiscoveryReport | None, _replace]

    # ── Study cycle ─────────────────────────────────────────────────────────
    study_plan: Annotated[StudyPlan | None, _replace]
    flashcards: Annotated[list[Flashcard], _append]
    quiz: Annotated[list[QuizQuestion], _append]

    # ── Direct answer ───────────────────────────────────────────────────────
    answer: Annotated[str, _replace]
    answer_expert: Annotated[str, _replace]


def make_initial_state(question: str = "", mode: Mode | str = "ask") -> OliviaState:
    """Return a fully-initialised blank state for a new cognitive cycle."""
    return OliviaState(
        messages=[],
        question=question,
        mode=mode,  # type: ignore[typeddict-item]
        phase="init",
        iteration=0,
        errors=[],
        papers=[],
        hypotheses=[],
        experiments=[],
        analyses=[],
        critique="",
        needs_revision=False,
        report=None,
        study_plan=None,
        flashcards=[],
        quiz=[],
        answer="",
        answer_expert="",
    )
