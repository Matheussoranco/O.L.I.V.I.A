"""Popperian critique — symbolic structural checks first, LLM review second.

The symbolic checks run offline and gate revision on their own; the LLM
critic (when available) adds depth but can never *remove* a symbolic finding.
"""

from __future__ import annotations

import logging
import re

from olivia.core.records import AnalysisResult, ExperimentPlan, Hypothesis
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import CRITIC_SYSTEM
from olivia.llm.structured import ask_json
from olivia.research.hypothesis import is_falsifiable

logger = logging.getLogger(__name__)

_MIN_SAMPLE = 10
_CIRCULAR_MARKERS = (
    "precisely the study that produces",
    "property being its capacity",
    "identified by the school's high performance",
    "means whatever",
    "as the classification guarantees",
    "derived from it",
    "computed from adaptivity",
)
_IMMUNISATION_MARKERS = (
    "misidentified",
    "mislabelled",
    "reclassified",
    "no trace apart",
    "permanent by its nature",
    "inner rhythm",
    "by selection",
    "by construction",
)
_UNIVERSAL_MARKERS = re.compile(r"\b(every|everyone|all|any learner|no item)\b", re.I)


def _symbolic_findings(
    hypotheses: list[Hypothesis],
    experiments: list[ExperimentPlan],
    analyses: list[AnalysisResult],
) -> list[str]:
    """Structural flaws detectable without any model."""
    findings: list[str] = []
    analysed_ids = {a.experiment_id for a in analyses}

    for h in hypotheses:
        text = " ".join([h.statement, *h.predictions, h.falsification_test]).casefold()
        if not is_falsifiable(h):
            findings.append(
                f"Hypothesis '{h.statement[:80]}…' is not falsifiable "
                "(missing predictions or a concrete refutation test)."
            )
        if any(marker in text for marker in _CIRCULAR_MARKERS):
            findings.append(
                f"Hypothesis '{h.statement[:80]}…' uses a circular operationalisation: "
                "the proposed cause or classification is defined by the outcome."
            )
        if any(marker in text for marker in _IMMUNISATION_MARKERS):
            findings.append(
                f"Hypothesis '{h.statement[:80]}…' immunises itself against disconfirmation "
                "by redefining failures or making the construct observationally empty."
            )
    for e in experiments:
        if not any(v.kind == "controlled" for v in e.variables):
            findings.append(
                f"Experiment {e.id} declares no controlled variables — confounds unmanaged."
            )
        if e.id not in analysed_ids:
            findings.append(f"Experiment {e.id} was designed but never analysed.")
        if e.sample_size is not None and e.sample_size < _MIN_SAMPLE:
            findings.append(
                f"Experiment {e.id} has sample size {e.sample_size} < {_MIN_SAMPLE} — underpowered."
            )
    for a in analyses:
        if a.p_value is not None and a.effect_size is None:
            findings.append(
                f"Analysis of {a.experiment_id} reports a p-value without an effect size."
            )
        if a.supports_hypothesis is False:
            findings.append(
                f"Analysis of {a.experiment_id} contradicts the hypothesis, but the cycle "
                "must not carry it forward as supported."
            )

    by_experiment = {e.id: e for e in experiments}
    for a in analyses:
        experiment = by_experiment.get(a.experiment_id)
        if experiment is None:
            continue
        matched = next((h for h in hypotheses if h.id == experiment.hypothesis_id), None)
        if matched is None:
            continue
        combined = f"{matched.statement} {a.summary}".casefold()
        if _UNIVERSAL_MARKERS.search(combined) and any(
            marker in combined
            for marker in ("one participant", "single ", "one case", "two of three")
        ):
            findings.append(
                f"Experiment {experiment.id} generalises a universal claim from a tiny "
                "or single-case observation."
            )
    return findings


def critique_research(
    question: str,
    hypotheses: list[Hypothesis],
    experiments: list[ExperimentPlan],
    analyses: list[AnalysisResult],
    client: LLMClient | None = None,
) -> tuple[str, bool]:
    """Review one research cycle; returns ``(critique_markdown, needs_revision)``."""
    client = client or get_client("strong")
    findings = _symbolic_findings(hypotheses, experiments, analyses)
    needs_revision = bool(findings)
    sections: list[str] = []
    if findings:
        sections.append("Structural checks:\n" + "\n".join(f"- {f}" for f in findings))

    if client.available:
        experiment_rows = [
            (e.design, [v.name for v in e.variables], e.sample_size) for e in experiments
        ]
        analysis_rows = [
            (a.summary, a.effect_size, a.p_value, a.supports_hypothesis) for a in analyses
        ]
        dump = (
            f"Question: {question}\n"
            f"Hypotheses: {[(h.statement, h.confidence) for h in hypotheses]}\n"
            f"Experiments: {experiment_rows}\n"
            f"Analyses: {analysis_rows}\n"
            f"Structural findings already flagged: {findings}\n\n"
            "Attack the weakest remaining link. Respond as JSON: "
            '{"critique": str, "needs_revision": bool, "fixes": [str]}.'
        )
        payload = ask_json(client, dump, system=CRITIC_SYSTEM)
        if isinstance(payload, dict):
            text = str(payload.get("critique", "")).strip()
            if text:
                sections.append("Reviewer critique:\n" + text)
            fixes = payload.get("fixes")
            if isinstance(fixes, list) and fixes:
                sections.append("Proposed fixes:\n" + "\n".join(f"- {f}" for f in map(str, fixes)))
            needs_revision = needs_revision or bool(payload.get("needs_revision"))

    if not sections:
        sections.append("No structural flaws found.")
    return "\n\n".join(sections), needs_revision
