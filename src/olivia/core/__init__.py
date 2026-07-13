"""Core package: records, state, and the cognitive graph."""

from olivia.core.graph import build_graph, run_cycle
from olivia.core.records import (
    AnalysisResult,
    DiscoveryReport,
    ExperimentPlan,
    Flashcard,
    Hypothesis,
    Paper,
    QuizQuestion,
    StudyPlan,
    Variable,
    new_id,
    to_dict,
)
from olivia.core.state import Mode, OliviaState, make_initial_state

__all__ = [
    "AnalysisResult",
    "DiscoveryReport",
    "ExperimentPlan",
    "Flashcard",
    "Hypothesis",
    "Mode",
    "OliviaState",
    "Paper",
    "QuizQuestion",
    "StudyPlan",
    "Variable",
    "build_graph",
    "make_initial_state",
    "new_id",
    "run_cycle",
    "to_dict",
]
