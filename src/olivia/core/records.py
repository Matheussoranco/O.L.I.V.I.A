"""Shared scientific/study data records — the single source of truth.

Every module (research, study, experts, agents, mcp) imports these from here;
nothing else may redefine them.  Plain dataclasses keep serialisation trivial
(``dataclasses.asdict``) and avoid heavyweight dependencies in the core.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


def new_id(prefix: str = "id") -> str:
    """Short unique identifier, e.g. ``hyp_3f9a2c1b``."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def to_dict(record: Any) -> dict[str, Any]:
    """Serialise any record dataclass to a plain dict."""
    return asdict(record)


# ---------------------------------------------------------------------------
# Research records
# ---------------------------------------------------------------------------


@dataclass
class Paper:
    """A bibliographic record from arXiv / Crossref / Semantic Scholar / manual."""

    id: str = field(default_factory=lambda: new_id("ppr"))
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    abstract: str = ""
    url: str = ""
    doi: str = ""
    venue: str = ""
    source: str = "manual"
    """Origin: 'arxiv' | 'crossref' | 'semanticscholar' | 'web' | 'manual'."""
    citations: int | None = None
    keywords: list[str] = field(default_factory=list)


@dataclass
class Hypothesis:
    """A falsifiable scientific hypothesis (Popperian by construction)."""

    id: str = field(default_factory=lambda: new_id("hyp"))
    statement: str = ""
    rationale: str = ""
    predictions: list[str] = field(default_factory=list)
    """Observable consequences that must hold if the hypothesis is true."""
    falsification_test: str = ""
    """The concrete test that could *refute* the hypothesis."""
    status: Literal["proposed", "supported", "refuted", "revised"] = "proposed"
    confidence: float = 0.5
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    parent_id: str | None = None
    """Set when this hypothesis is a revision of an earlier one."""


@dataclass
class Variable:
    """An experimental variable."""

    name: str = ""
    kind: Literal["independent", "dependent", "controlled", "confound"] = "independent"
    description: str = ""


@dataclass
class ExperimentPlan:
    """A concrete experiment design derived from a hypothesis."""

    id: str = field(default_factory=lambda: new_id("exp"))
    hypothesis_id: str = ""
    design: str = ""
    """e.g. 'randomised controlled', 'A/B', 'simulation', 'observational'."""
    variables: list[Variable] = field(default_factory=list)
    procedure: list[str] = field(default_factory=list)
    sample_size: int | None = None
    power: float | None = None
    materials: list[str] = field(default_factory=list)
    analysis_plan: str = ""
    code: str = ""
    """Optional Python simulation/analysis code, runnable via tools.python_exec."""
    risks: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Statistical outcome of an experiment."""

    experiment_id: str = ""
    summary: str = ""
    statistics: dict[str, float] = field(default_factory=dict)
    effect_size: float | None = None
    p_value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    interpretation: str = ""
    supports_hypothesis: bool | None = None


@dataclass
class DiscoveryReport:
    """The end-to-end product of one research cycle."""

    question: str = ""
    papers: list[Paper] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    experiments: list[ExperimentPlan] = field(default_factory=list)
    analyses: list[AnalysisResult] = field(default_factory=list)
    conclusion: str = ""
    open_questions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    report_markdown: str = ""


# ---------------------------------------------------------------------------
# Study records
# ---------------------------------------------------------------------------


@dataclass
class Flashcard:
    """An SM-2 spaced-repetition card."""

    id: str = field(default_factory=lambda: new_id("card"))
    front: str = ""
    back: str = ""
    topic: str = ""
    ease: float = 2.5
    interval_days: float = 0.0
    repetitions: int = 0
    due: str = ""
    """ISO-8601 date the card is next due."""


@dataclass
class QuizQuestion:
    """A quiz item; multiple-choice when ``options`` is non-empty."""

    id: str = field(default_factory=lambda: new_id("qq"))
    prompt: str = ""
    options: list[str] = field(default_factory=list)
    answer_index: int | None = None
    answer_text: str = ""
    explanation: str = ""
    difficulty: Literal["easy", "medium", "hard"] = "medium"


@dataclass
class StudyPlan:
    """A structured curriculum for learning a topic."""

    topic: str = ""
    goal: str = ""
    prerequisites: list[str] = field(default_factory=list)
    milestones: list[dict[str, Any]] = field(default_factory=list)
    """Each: {'week': int, 'title': str, 'objectives': [str], 'practice': str}."""
    resources: list[str] = field(default_factory=list)
    hours_per_week: float = 5.0
    weeks: int = 4
