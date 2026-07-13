"""Experiment design — turn a hypothesis into a concrete, powered plan.

The LLM proposes design, variables, procedure, and (when the experiment is a
simulation) runnable Python code that prints one final JSON object; sample
size comes from a symbolic power analysis, never from the model's guess.
"""

from __future__ import annotations

import logging

from olivia.core.records import ExperimentPlan, Hypothesis, Variable
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import RESEARCH_SYSTEM
from olivia.llm.structured import ask_json
from olivia.tools.science import required_sample_size

logger = logging.getLogger(__name__)

_VALID_KINDS = ("independent", "dependent", "controlled", "confound")


def _coerce_variables(raw: object) -> list[Variable]:
    variables: list[Variable] = []
    if not isinstance(raw, list):
        return variables
    for item in raw:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            continue
        kind = str(item.get("kind", "controlled")).lower()
        variables.append(
            Variable(
                name=str(item["name"]).strip(),
                kind=kind if kind in _VALID_KINDS else "controlled",  # type: ignore[arg-type]
                description=str(item.get("description", "")).strip(),
            )
        )
    return variables


def _str_list(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [str(raw).strip()] if raw else []


def design_experiment(
    hypothesis: Hypothesis,
    client: LLMClient | None = None,
) -> ExperimentPlan:
    """Design one experiment capable of falsifying ``hypothesis``."""
    client = client or get_client("strong")

    if client.available:
        prompt = (
            f"Hypothesis: {hypothesis.statement}\n"
            f"Predictions: {hypothesis.predictions}\n"
            f"Falsification test: {hypothesis.falsification_test}\n\n"
            "Design ONE rigorous experiment that could falsify this hypothesis. "
            "Respond as JSON:\n"
            '{"design": "randomised controlled | A/B | simulation | observational", '
            '"variables": [{"name": str, "kind": "independent|dependent|controlled|confound", '
            '"description": str}], "procedure": [str], "expected_effect_size": number or null, '
            '"analysis_plan": str, "materials": [str], "risks": [str], '
            '"code": "OPTIONAL runnable pure-Python simulation of the experiment that prints '
            'exactly one final JSON object like {\\"effect_size\\": ..., \\"p_value\\": ..., '
            '\\"statistics\\": {...}} to stdout — stdlib only, deterministic seed"}'
        )
        payload = ask_json(client, prompt, system=RESEARCH_SYSTEM, max_tokens=3000)
        if isinstance(payload, dict):
            plan = ExperimentPlan(
                hypothesis_id=hypothesis.id,
                design=str(payload.get("design", "simulation")).strip() or "simulation",
                variables=_coerce_variables(payload.get("variables")),
                procedure=_str_list(payload.get("procedure")),
                analysis_plan=str(payload.get("analysis_plan", "")).strip(),
                materials=_str_list(payload.get("materials")),
                risks=_str_list(payload.get("risks")),
                code=str(payload.get("code") or "").strip(),
            )
            effect = payload.get("expected_effect_size")
            if isinstance(effect, (int, float)) and effect > 0:
                plan.sample_size = required_sample_size(float(effect))
                plan.power = 0.8
            return plan
        logger.info("Experiment design fell back: unparseable LLM output")

    # Offline template — a minimal simulation design tied to the predictions.
    prediction = hypothesis.predictions[0] if hypothesis.predictions else hypothesis.statement
    return ExperimentPlan(
        hypothesis_id=hypothesis.id,
        design="simulation",
        variables=[
            Variable(
                name="candidate_factor",
                kind="independent",
                description="The manipulated factor named by the hypothesis.",
            ),
            Variable(
                name="outcome",
                kind="dependent",
                description=f"The measurable outcome in: {prediction[:160]}",
            ),
        ],
        procedure=[
            "Define a measurable operationalisation of the outcome.",
            "Vary the independent factor across at least two conditions.",
            "Hold all other known factors constant (controls).",
            "Compare outcomes across conditions with an effect-size estimate.",
        ],
        analysis_plan="Welch's t-test between conditions; report Cohen's d with a 95% CI.",
        risks=["Offline template design — operationalisation must be reviewed by a human."],
    )
