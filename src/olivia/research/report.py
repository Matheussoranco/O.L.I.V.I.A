"""Discovery report — deterministic IMRaD-ish markdown, LLM-polished conclusion.

The skeleton is assembled symbolically from the cycle's records, so a report
always exists offline; when a model is available it contributes only the
conclusion, open questions, and a calibrated confidence.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from statistics import fmean

from olivia.core.records import (
    AnalysisResult,
    DiscoveryReport,
    ExperimentPlan,
    Hypothesis,
    Paper,
)
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import WRITER_SYSTEM
from olivia.llm.structured import ask_json

logger = logging.getLogger(__name__)


def _supported_ids(analyses: list[AnalysisResult], experiments: list[ExperimentPlan]) -> set[str]:
    """Hypothesis ids whose experiments produced supporting analyses."""
    by_experiment = {e.id: e.hypothesis_id for e in experiments}
    return {
        by_experiment[a.experiment_id]
        for a in analyses
        if a.supports_hypothesis and a.experiment_id in by_experiment
    }


def _fallback_conclusion(
    hypotheses: list[Hypothesis], supported: set[str], analyses: list[AnalysisResult]
) -> str:
    tested = sum(1 for a in analyses if a.supports_hypothesis is not None)
    return (
        f"{len(supported)} of {len(hypotheses)} hypotheses were supported by the "
        f"{tested} conclusive analyses in this cycle. "
        + (
            "The supported hypotheses warrant replication with pre-registered designs."
            if supported
            else "No hypothesis found support; the question remains open."
        )
    )


def _markdown(
    question: str,
    papers: list[Paper],
    hypotheses: list[Hypothesis],
    experiments: list[ExperimentPlan],
    analyses: list[AnalysisResult],
    critique: str,
    conclusion: str,
    open_questions: list[str],
) -> str:
    lines = [f"# Discovery Report: {question}", ""]

    lines.append("## Literature")
    if papers:
        lines += [
            f"{i}. {p.title} ({p.year or 'n.d.'}, {p.venue or p.source})"
            for i, p in enumerate(papers, 1)
        ]
    else:
        lines.append("_No literature retrieved._")

    lines += ["", "## Hypotheses"]
    for h in hypotheses:
        lines += [
            f"- **{h.statement}**",
            f"  - status: {h.status}, confidence: {h.confidence:.2f}",
            f"  - falsification test: {h.falsification_test or '—'}",
        ]

    lines += ["", "## Experiments"]
    if experiments:
        for e in experiments:
            variables = ", ".join(f"{v.name} ({v.kind})" for v in e.variables) or "—"
            sample = f", n = {e.sample_size}/group" if e.sample_size else ""
            lines.append(f"- **{e.id}** — {e.design}{sample}; variables: {variables}")
    else:
        lines.append("_No experiments designed._")

    lines += ["", "## Results"]
    if analyses:
        for a in analyses:
            effect = f"d = {a.effect_size:.3f}" if a.effect_size is not None else "d = —"
            p = f"p = {a.p_value:.4g}" if a.p_value is not None else "p = —"
            verdict = {True: "supports", False: "refutes", None: "inconclusive"}[
                a.supports_hypothesis
            ]
            lines.append(f"- {a.experiment_id}: {a.summary} ({effect}, {p}) → **{verdict}**")
    else:
        lines.append("_No analyses run._")

    lines += ["", "## Limitations", critique or "_No critique recorded._"]
    lines += ["", "## Conclusion", conclusion]
    lines += ["", "## Open Questions"]
    lines += [f"- {q}" for q in open_questions] or ["_None recorded._"]
    return "\n".join(lines)


def write_report(
    question: str,
    papers: list[Paper],
    hypotheses: list[Hypothesis],
    experiments: list[ExperimentPlan],
    analyses: list[AnalysisResult],
    critique: str = "",
    client: LLMClient | None = None,
) -> DiscoveryReport:
    """Assemble the end-to-end product of one research cycle."""
    client = client or get_client("strong")
    supported = _supported_ids(analyses, experiments)

    supported_confidences = [h.confidence for h in hypotheses if h.id in supported]
    confidence = fmean(supported_confidences) if supported_confidences else 0.0
    conclusion = _fallback_conclusion(hypotheses, supported, analyses)
    open_questions = [
        f"What alternative operationalisation would decisively test: {h.statement[:120]}?"
        for h in hypotheses
        if h.id not in supported
    ]

    if client.available:
        prompt = (
            f"Question: {question}\n"
            f"Hypotheses: {[(h.statement, h.id in supported) for h in hypotheses]}\n"
            f"Key results: {[(a.summary, a.effect_size, a.p_value) for a in analyses]}\n"
            f"Critique: {critique[:800]}\n\n"
            "Write the closing of a discovery report. Respond as JSON: "
            '{"conclusion": "2-4 precise sentences, every claim grounded in the results above", '
            '"open_questions": [str], "confidence": 0..1}.'
        )
        payload = ask_json(client, prompt, system=WRITER_SYSTEM)
        if isinstance(payload, dict):
            conclusion = str(payload.get("conclusion", "")).strip() or conclusion
            if isinstance(payload.get("open_questions"), list):
                open_questions = [str(q) for q in payload["open_questions"] if str(q).strip()]
            with suppress(TypeError, ValueError):
                confidence = min(max(float(payload.get("confidence", confidence)), 0.0), 1.0)

    return DiscoveryReport(
        question=question,
        papers=papers,
        hypotheses=hypotheses,
        experiments=experiments,
        analyses=analyses,
        conclusion=conclusion,
        open_questions=open_questions,
        confidence=confidence,
        report_markdown=_markdown(
            question, papers, hypotheses, experiments, analyses, critique, conclusion,
            open_questions,
        ),
    )
