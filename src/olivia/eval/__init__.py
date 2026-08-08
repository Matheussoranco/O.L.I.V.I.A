"""O.L.I.V.I.A. evaluation harness — measured claims, not adjectives.

Three held-out suites, each with a scoring function and no tuning loop:

* ``symbolic`` — STEM solving accuracy, with the symbolic-first path and the
  LLM fallback path scored **separately** so a regression in one cannot hide
  behind the other.
* ``research`` — does the Popperian critique catch deliberately flawed
  hypotheses, and does it leave sound controls alone? Catch rate *and*
  false-alarm rate, because a critic that rejects everything is not a critic.
* ``study`` — SM-2 scheduling against an independent reference implementation,
  quiz grading correctness, and flashcard/quiz generation fidelity.

Every suite runs offline. Suites that need a model report ``skipped`` with a
reason rather than failing, so CI is never red for lack of a key.
"""

from __future__ import annotations

from olivia.eval.harness import (
    CaseResult,
    EvalRun,
    Metric,
    SuiteReport,
    check_gates,
    load_dataset,
    load_gates,
    run_all,
    run_suite,
    run_to_markdown,
    suite_names,
)

__all__ = [
    "CaseResult",
    "EvalRun",
    "Metric",
    "SuiteReport",
    "check_gates",
    "load_dataset",
    "load_gates",
    "run_all",
    "run_suite",
    "run_to_markdown",
    "suite_names",
]
