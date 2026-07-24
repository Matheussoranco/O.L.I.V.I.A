"""Analysis — execute the experiment and read off the statistics.

Measurement beats reasoning: when the plan carries simulation code we run it
in the sandbox and parse the JSON it prints; the LLM is only consulted for
codeless plans, and its output is explicitly labelled reasoning, not data.
"""

from __future__ import annotations

import logging

from olivia.core.records import AnalysisResult, ExperimentPlan
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import RESEARCH_SYSTEM
from olivia.llm.structured import ask_json, extract_json
from olivia.tools.science import python_exec

logger = logging.getLogger(__name__)

_ALPHA = 0.05


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _from_execution(plan: ExperimentPlan, output: dict) -> AnalysisResult:
    """Build an AnalysisResult from a sandbox run's stdout JSON."""
    payload = extract_json(output.get("stdout", "")) or {}
    if not isinstance(payload, dict):
        payload = {}

    statistics = (
        {k: v for k, v in (payload.get("statistics") or {}).items() if isinstance(v, (int, float))}
        if isinstance(payload.get("statistics"), dict)
        else {}
    )
    effect_size = _as_float(payload.get("effect_size"))
    p_value = _as_float(payload.get("p_value"))
    supports = p_value is not None and p_value < _ALPHA

    pieces = [f"Simulation executed ({plan.design})."]
    if effect_size is not None:
        pieces.append(f"effect size = {effect_size:.3f}")
    if p_value is not None:
        pieces.append(f"p = {p_value:.4g}")
    if not payload:
        pieces.append("stdout contained no parseable JSON — result inconclusive")

    return AnalysisResult(
        experiment_id=plan.id,
        summary="; ".join(pieces),
        statistics=statistics,
        effect_size=effect_size,
        ci_low=_as_float(payload.get("ci_low")),
        ci_high=_as_float(payload.get("ci_high")),
        p_value=p_value,
        interpretation=(
            f"Measured outcome of executed simulation code (alpha = {_ALPHA})."
            if payload
            else "Execution succeeded but produced no structured result."
        ),
        supports_hypothesis=supports if payload else None,
    )


def run_analysis(
    plan: ExperimentPlan,
    client: LLMClient | None = None,
) -> AnalysisResult:
    """Analyse one experiment plan: execute code, or reason, or abstain."""
    client = client or get_client()

    if plan.code.strip():
        output = python_exec(plan.code, timeout=60.0)
        if output.get("ok"):
            return _from_execution(plan, output)
        stderr_tail = (output.get("stderr") or "unknown error")[-500:]
        return AnalysisResult(
            experiment_id=plan.id,
            summary=f"Simulation failed to execute: {stderr_tail}",
            interpretation="No measurement available; the experiment code errored.",
            supports_hypothesis=None,
        )

    if client.available:
        prompt = (
            f"Experiment design: {plan.design}\n"
            f"Procedure: {plan.procedure}\n"
            f"Analysis plan: {plan.analysis_plan}\n\n"
            "No executable code or data is available. Reason about the most likely "
            "outcome and its interpretation. Respond as JSON: "
            '{"summary": str, "interpretation": str, "supports_hypothesis": true|false|null}.'
        )
        payload = ask_json(client, prompt, system=RESEARCH_SYSTEM)
        if isinstance(payload, dict):
            supports = payload.get("supports_hypothesis")
            return AnalysisResult(
                experiment_id=plan.id,
                summary=str(payload.get("summary", "")).strip(),
                interpretation=(
                    "REASONED, NOT MEASURED: " + str(payload.get("interpretation", "")).strip()
                ),
                supports_hypothesis=supports if isinstance(supports, bool) else None,
            )

    return AnalysisResult(
        experiment_id=plan.id,
        summary="inconclusive — no executable experiment code",
        interpretation="Neither simulation code nor an LLM backend was available.",
        supports_hypothesis=None,
    )
