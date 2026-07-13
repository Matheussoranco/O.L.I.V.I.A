"""Research package: the scientific discovery cycle, step by step.

literature → hypothesis → experiment → analysis → critique → report.
Orchestration lives in :mod:`olivia.core.graph`; each step here is pure and
independently testable.
"""

from olivia.research.analysis import run_analysis
from olivia.research.critic import critique_research
from olivia.research.experiment import design_experiment
from olivia.research.hypothesis import (
    generate_hypotheses,
    is_falsifiable,
    revise_hypothesis,
)
from olivia.research.literature import review_literature
from olivia.research.report import write_report

__all__ = [
    "critique_research",
    "design_experiment",
    "generate_hypotheses",
    "is_falsifiable",
    "review_literature",
    "revise_hypothesis",
    "run_analysis",
    "write_report",
]
