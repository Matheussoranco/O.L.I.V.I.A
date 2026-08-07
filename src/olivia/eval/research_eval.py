"""Research-cycle quality — does the Popperian critique catch bad science?

Two numbers, always together:

* **catch rate** — the fraction of deliberately flawed cycles the critic sends
  back for revision;
* **false-alarm rate** — the fraction of *sound* control cycles it sends back
  anyway.

Either alone is trivially gamed. A critic that flags everything scores a
perfect catch rate; a critic that flags nothing scores a perfect false-alarm
rate. Both degenerate critics score 0 on Youden's J (``catch - false_alarm``)
and 0.5 on balanced accuracy, which is why those are the headline metrics.

The symbolic critic is scored offline; when a model is configured, the LLM
critic is scored under its own metric names, never merged into the symbolic
ones.
"""

from __future__ import annotations

from typing import Any

from olivia.core.records import AnalysisResult, ExperimentPlan, Hypothesis, Variable
from olivia.eval.harness import (
    CaseResult,
    Metric,
    SuiteReport,
    load_dataset,
    ratio,
    register_suite,
)
from olivia.llm.client import LLMClient, NullClient


# ---------------------------------------------------------------------------
# JSON -> records
# ---------------------------------------------------------------------------


def _hypothesis(payload: dict[str, Any]) -> Hypothesis:
    return Hypothesis(
        id=payload.get("id", "h1"),
        statement=payload.get("statement", ""),
        rationale=payload.get("rationale", ""),
        predictions=list(payload.get("predictions", [])),
        falsification_test=payload.get("falsification_test", ""),
        status=payload.get("status", "proposed"),
        confidence=float(payload.get("confidence", 0.5)),
        evidence_for=list(payload.get("evidence_for", [])),
        evidence_against=list(payload.get("evidence_against", [])),
    )


def _experiment(payload: dict[str, Any]) -> ExperimentPlan:
    return ExperimentPlan(
        id=payload.get("id", "e1"),
        hypothesis_id=payload.get("hypothesis_id", ""),
        design=payload.get("design", ""),
        variables=[
            Variable(
                name=v.get("name", ""),
                kind=v.get("kind", "independent"),
                description=v.get("description", ""),
            )
            for v in payload.get("variables", [])
        ],
        procedure=list(payload.get("procedure", [])),
        sample_size=payload.get("sample_size"),
        analysis_plan=payload.get("analysis_plan", ""),
    )


def _analysis(payload: dict[str, Any]) -> AnalysisResult:
    return AnalysisResult(
        experiment_id=payload.get("experiment_id", ""),
        summary=payload.get("summary", ""),
        statistics=dict(payload.get("statistics", {})),
        effect_size=payload.get("effect_size"),
        p_value=payload.get("p_value"),
        ci_low=payload.get("ci_low"),
        ci_high=payload.get("ci_high"),
        interpretation=payload.get("interpretation", ""),
        supports_hypothesis=payload.get("supports_hypothesis"),
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _judge(case: dict[str, Any], flagged: bool, critique: str) -> CaseResult:
    """A flawed case is scored on being caught; a sound one on being left alone."""
    is_flawed = case["label"] == "flawed"
    right_call = flagged if is_flawed else not flagged
    return CaseResult(
        id=case["id"],
        outcome="correct" if right_call else "wrong",
        group=case["family"],
        expected="needs_revision" if is_flawed else "clean",
        got="needs_revision" if flagged else "clean",
        detail=case.get("flaw", ""),
        meta={
            "label": case["label"],
            "family": case["family"],
            "flagged": flagged,
            "critique": critique,
        },
    )


def _decision_metrics(cases: list[CaseResult], prefix: str) -> list[Metric]:
    flawed = [c for c in cases if c.meta["label"] == "flawed"]
    sound = [c for c in cases if c.meta["label"] == "sound"]
    caught = sum(1 for c in flawed if c.meta["flagged"])
    false_alarms = sum(1 for c in sound if c.meta["flagged"])
    catch_rate = ratio(caught, len(flawed))
    false_alarm_rate = ratio(false_alarms, len(sound))
    metrics = [
        Metric(f"{prefix}catch_rate", catch_rate, len(flawed), "flawed cycles sent for revision"),
        Metric(
            f"{prefix}false_alarm_rate",
            false_alarm_rate,
            len(sound),
            "sound controls wrongly flagged",
        ),
        Metric(
            f"{prefix}balanced_accuracy",
            (catch_rate + (1.0 - false_alarm_rate)) / 2.0,
            len(cases),
            "0.5 for a critic that always (or never) flags",
        ),
        Metric(
            f"{prefix}youden_j",
            catch_rate - false_alarm_rate,
            len(cases),
            "0.0 for either degenerate critic",
        ),
    ]
    families: dict[str, list[CaseResult]] = {}
    for case in flawed:
        families.setdefault(case.group, []).append(case)
    metrics += [
        Metric(
            f"{prefix}catch.{family}",
            ratio(sum(1 for c in rows if c.meta["flagged"]), len(rows)),
            len(rows),
        )
        for family, rows in sorted(families.items())
    ]
    return metrics


def _run_pass(
    cases: list[dict[str, Any]], client: LLMClient, prefix: str
) -> tuple[list[CaseResult], list[Metric]]:
    from olivia.research.critic import critique_research

    results: list[CaseResult] = []
    for case in cases:
        critique, needs_revision = critique_research(
            case["question"],
            [_hypothesis(h) for h in case["hypotheses"]],
            [_experiment(e) for e in case["experiments"]],
            [_analysis(a) for a in case["analyses"]],
            client=client,
        )
        results.append(_judge(case, bool(needs_revision), critique))
    return results, _decision_metrics(results, prefix)


def run(client: LLMClient | None = None) -> SuiteReport:
    data = load_dataset("research_critique")
    cases: list[dict[str, Any]] = data["cases"]
    report = SuiteReport(suite="research")

    symbolic_cases, symbolic_metrics = _run_pass(cases, NullClient(), "symbolic.")
    report.cases = symbolic_cases
    report.metrics = symbolic_metrics

    missed = [c for c in symbolic_cases if c.outcome == "wrong" and c.meta["label"] == "flawed"]
    if missed:
        families = sorted({c.group for c in missed})
        report.notes.append(
            f"symbolic critic missed {len(missed)} flawed cycles, in: {', '.join(families)}"
        )

    if client is None or not client.available:
        report.notes.append("LLM critic not measured: no LLM backend configured")
        report.metrics.append(Metric("llm.measured", 0.0, len(cases), "no LLM backend"))
        return report

    llm_cases, llm_metrics = _run_pass(cases, client, "llm.")
    for case in llm_cases:
        case.id = f"{case.id}@llm"
    report.cases += llm_cases
    report.metrics += llm_metrics
    report.metrics.append(Metric("llm.measured", 1.0, len(llm_cases), "cases re-scored with a model"))
    return report


register_suite("research", run)
