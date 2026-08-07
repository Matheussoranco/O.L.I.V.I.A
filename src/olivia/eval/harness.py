"""Evaluation primitives: cases, metrics, suite registry, gates, reporting.

The harness is deliberately dependency-free and offline-first.  A suite is any
callable ``(client) -> SuiteReport``; it must never raise for a missing model,
only report ``skipped`` with a reason.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from olivia.llm.client import LLMClient

DATASET_DIR = Path(__file__).parent / "datasets"

Outcome = Literal["correct", "wrong", "abstain", "skipped"]


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    """One scored eval case.

    ``wrong`` and ``abstain`` are kept apart on purpose: a confidently wrong
    answer is a worse failure than an honest "I cannot solve this".
    """

    id: str
    outcome: Outcome = "abstain"
    group: str = ""
    """Slice this case belongs to (domain, flaw family, tier…)."""
    expected: str = ""
    got: str = ""
    detail: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Metric:
    """A single measured number, with the sample size that produced it."""

    name: str
    value: float
    n: int = 0
    note: str = ""

    def as_percent(self) -> str:
        return f"{100 * self.value:.1f}%"


@dataclass
class SuiteReport:
    """Everything one suite measured."""

    suite: str
    metrics: list[Metric] = field(default_factory=list)
    cases: list[CaseResult] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    notes: list[str] = field(default_factory=list)

    def metric(self, name: str) -> Metric | None:
        return next((m for m in self.metrics if m.name == name), None)

    def value(self, name: str, default: float = 0.0) -> float:
        found = self.metric(name)
        return found.value if found else default


@dataclass
class EvalRun:
    """A full run over one or more suites."""

    reports: list[SuiteReport] = field(default_factory=list)
    llm_backend: str = "none"

    def report(self, suite: str) -> SuiteReport | None:
        return next((r for r in self.reports if r.suite == suite), None)

    def flat_metrics(self) -> dict[str, float]:
        """``{'suite.metric': value}`` — the form gates are written against."""
        flat: dict[str, float] = {}
        for report in self.reports:
            if report.skipped:
                continue
            for metric in report.metrics:
                flat[f"{report.suite}.{metric.name}"] = metric.value
        return flat


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def ratio(numerator: int, denominator: int) -> float:
    """Safe division; an empty denominator scores 0.0, never NaN."""
    return numerator / denominator if denominator else 0.0


def tally(cases: list[CaseResult], outcome: Outcome) -> int:
    return sum(1 for c in cases if c.outcome == outcome)


def accuracy_metrics(cases: list[CaseResult], prefix: str = "") -> list[Metric]:
    """The standard correct / wrong / abstain triple over a case list.

    ``precision`` is accuracy over the cases the system chose to answer — the
    number that says how much a produced answer can be trusted.
    """
    total = len(cases)
    correct = tally(cases, "correct")
    wrong = tally(cases, "wrong")
    attempted = correct + wrong
    return [
        Metric(f"{prefix}accuracy", ratio(correct, total), total),
        Metric(f"{prefix}precision", ratio(correct, attempted), attempted, "over answered cases"),
        Metric(f"{prefix}wrong_rate", ratio(wrong, total), total, "confidently wrong"),
        Metric(f"{prefix}abstain_rate", ratio(total - attempted, total), total),
    ]


def group_accuracy(cases: list[CaseResult], prefix: str = "") -> list[Metric]:
    """Accuracy broken down by ``CaseResult.group``."""
    groups: dict[str, list[CaseResult]] = {}
    for case in cases:
        groups.setdefault(case.group or "ungrouped", []).append(case)
    return [
        Metric(f"{prefix}{name}.accuracy", ratio(tally(rows, "correct"), len(rows)), len(rows))
        for name, rows in sorted(groups.items())
    ]


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


def load_dataset(name: str) -> Any:
    """Load a held-out dataset shipped inside the package."""
    path = DATASET_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"eval dataset not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_gates() -> dict[str, float]:
    """Regression floors, keyed ``suite.metric``."""
    return {k: float(v) for k, v in load_dataset("gates").get("floors", {}).items()}


# ---------------------------------------------------------------------------
# Suite registry
# ---------------------------------------------------------------------------

SuiteFn = Callable[[LLMClient | None], SuiteReport]
_REGISTRY: dict[str, SuiteFn] = {}


def register_suite(name: str, fn: SuiteFn) -> None:
    _REGISTRY[name] = fn


def suite_names() -> list[str]:
    _load_suites()
    return list(_REGISTRY)


def _load_suites() -> None:
    if _REGISTRY:
        return
    # Imported for their registration side-effect; kept lazy so `import
    # olivia.eval` stays cheap and sympy-free until a suite actually runs.
    from olivia.eval import research_eval, study_eval, symbolic_eval  # noqa: F401


def run_suite(name: str, client: LLMClient | None = None) -> SuiteReport:
    _load_suites()
    if name not in _REGISTRY:
        raise KeyError(f"unknown eval suite '{name}' (have: {', '.join(_REGISTRY)})")
    return _REGISTRY[name](client)


def run_all(client: LLMClient | None = None, suites: list[str] | None = None) -> EvalRun:
    """Run every registered suite (or the named subset)."""
    _load_suites()
    chosen = suites or list(_REGISTRY)
    reports = [run_suite(name, client) for name in chosen]
    backend = client.name if client is not None and client.available else "none"
    return EvalRun(reports=reports, llm_backend=backend)


# ---------------------------------------------------------------------------
# Gates and reporting
# ---------------------------------------------------------------------------


def check_gates(run: EvalRun, gates: dict[str, float] | None = None) -> list[str]:
    """Return one message per breached floor; empty means no regression.

    A gate whose metric is missing (its suite was skipped) is *not* a failure —
    CI must never go red because a key is absent.
    """
    gates = load_gates() if gates is None else gates
    measured = run.flat_metrics()
    breaches: list[str] = []
    for key, floor in sorted(gates.items()):
        if key not in measured:
            continue
        if measured[key] + 1e-9 < floor:
            breaches.append(f"{key}: {measured[key]:.4f} < floor {floor:.4f}")
    return breaches


def run_to_dict(run: EvalRun) -> dict[str, Any]:
    return {
        "llm_backend": run.llm_backend,
        "metrics": run.flat_metrics(),
        "suites": [asdict(r) for r in run.reports],
    }


def run_to_markdown(run: EvalRun, verbose: bool = False) -> str:
    """Human-readable scoreboard."""
    lines = ["# O.L.I.V.I.A. eval run", "", f"LLM backend: `{run.llm_backend}`", ""]
    for report in run.reports:
        lines.append(f"## {report.suite}")
        lines.append("")
        if report.skipped:
            lines += [f"_skipped: {report.skip_reason}_", ""]
            continue
        lines += ["| metric | value | n | note |", "|---|---|---|---|"]
        for metric in report.metrics:
            lines.append(
                f"| `{metric.name}` | {metric.as_percent()} | {metric.n} | {metric.note} |"
            )
        lines.append("")
        for note in report.notes:
            lines.append(f"- {note}")
        if report.notes:
            lines.append("")
        if verbose:
            failures = [c for c in report.cases if c.outcome in ("wrong", "abstain")]
            if failures:
                lines += ["<details><summary>failing cases</summary>", ""]
                for case in failures:
                    lines.append(
                        f"- `{case.id}` [{case.outcome}] expected `{case.expected}` "
                        f"got `{case.got}` {case.detail}"
                    )
                lines += ["", "</details>", ""]
    return "\n".join(lines).rstrip() + "\n"
