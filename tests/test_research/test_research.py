"""Research cycle — falsifiability gates, offline templates, LLM parsing."""

from __future__ import annotations

import json

from olivia.core.records import AnalysisResult, ExperimentPlan, Hypothesis, Paper, Variable
from olivia.llm.client import NullClient
from olivia.research import (
    critique_research,
    design_experiment,
    generate_hypotheses,
    is_falsifiable,
    review_literature,
    revise_hypothesis,
    run_analysis,
    write_report,
)


def _good_hypothesis(**overrides) -> Hypothesis:
    fields = dict(
        statement="Spacing reviews increases retention.",
        predictions=["Spaced group scores higher at 30 days."],
        falsification_test="Randomise spacing; equal scores refute it.",
    )
    fields.update(overrides)
    return Hypothesis(**fields)


# ---------------------------------------------------------------------------
# is_falsifiable
# ---------------------------------------------------------------------------


def test_is_falsifiable_accepts_complete_hypothesis():
    assert is_falsifiable(_good_hypothesis())


def test_is_falsifiable_requires_test_and_predictions():
    assert not is_falsifiable(_good_hypothesis(falsification_test="  "))
    assert not is_falsifiable(_good_hypothesis(predictions=[]))


def test_is_falsifiable_rejects_untestable_wording():
    h = _good_hypothesis(statement="This holds in every possible world and cannot be tested.")
    assert not is_falsifiable(h)


# ---------------------------------------------------------------------------
# generate / revise hypotheses
# ---------------------------------------------------------------------------


def test_generate_hypotheses_offline_template():
    hypotheses = generate_hypotheses("Why do we sleep?", [], client=NullClient())
    assert len(hypotheses) == 1
    h = hypotheses[0]
    assert h.confidence == 0.3
    assert is_falsifiable(h)
    assert "Why do we sleep?" in h.statement


def test_generate_hypotheses_drops_unfalsifiable_llm_output(fake_client):
    payload = [
        {
            "statement": "Sleep consolidates memory.",
            "predictions": ["Sleep-deprived recall drops."],
            "falsification_test": "Deprivation study with equal recall refutes it.",
            "confidence": 0.7,
        },
        {
            "statement": "Sleep is beneficial in ways that cannot be measured.",
            "predictions": ["none"],
            "falsification_test": "",
        },
    ]
    hypotheses = generate_hypotheses("Why sleep?", [], client=fake_client(json.dumps(payload)))
    assert [h.statement for h in hypotheses] == ["Sleep consolidates memory."]
    assert hypotheses[0].confidence == 0.7


def test_generate_hypotheses_clamps_confidence(fake_client):
    payload = [
        {
            "statement": "S",
            "predictions": ["p"],
            "falsification_test": "t",
            "confidence": 7,
        }
    ]
    (h,) = generate_hypotheses("q", [], client=fake_client(json.dumps(payload)))
    assert h.confidence == 1.0


def test_revise_hypothesis_offline_makes_low_confidence_child():
    parent = _good_hypothesis(confidence=0.5)
    child = revise_hypothesis(parent, "sample too small", client=NullClient())
    assert child.parent_id == parent.id
    assert child.id != parent.id
    assert child.confidence == 0.4
    assert "sample too small" in child.rationale


def test_revise_hypothesis_llm_child_keeps_lineage(fake_client):
    parent = _good_hypothesis()
    payload = {
        "statement": "Spacing helps only beyond 24h gaps.",
        "predictions": ["No gain for <24h gaps."],
        "falsification_test": "Compare 1h vs 48h gaps.",
        "confidence": 0.6,
    }
    client = fake_client(json.dumps(payload))
    child = revise_hypothesis(parent, "gap size unaddressed", client=client)
    assert child.parent_id == parent.id
    assert child.statement == "Spacing helps only beyond 24h gaps."


# ---------------------------------------------------------------------------
# design_experiment
# ---------------------------------------------------------------------------


def test_design_experiment_offline_template():
    plan = design_experiment(_good_hypothesis(), client=NullClient())
    assert plan.design == "simulation"
    kinds = {v.kind for v in plan.variables}
    assert {"independent", "dependent"} <= kinds
    assert plan.code == ""
    assert plan.risks  # flags itself as a template needing human review


def test_design_experiment_sample_size_is_symbolic_not_llm(fake_client):
    payload = {
        "design": "randomised controlled",
        "variables": [{"name": "gap", "kind": "independent"}],
        "procedure": ["randomise", "test"],
        "expected_effect_size": 0.5,
        "analysis_plan": "t-test",
        "code": "",
    }
    plan = design_experiment(_good_hypothesis(), client=fake_client(json.dumps(payload)))
    assert plan.sample_size == 63  # required_sample_size(0.5), not a model guess
    assert plan.power == 0.8
    assert plan.hypothesis_id


# ---------------------------------------------------------------------------
# run_analysis
# ---------------------------------------------------------------------------


def test_run_analysis_executes_code_and_reads_stats():
    code = 'import json; print(json.dumps({"effect_size": 0.8, "p_value": 0.01}))'
    plan = ExperimentPlan(design="simulation", code=code)
    result = run_analysis(plan, client=NullClient())
    assert result.effect_size == 0.8
    assert result.p_value == 0.01
    assert result.supports_hypothesis is True


def test_run_analysis_nonsignificant_does_not_support():
    code = 'import json; print(json.dumps({"effect_size": 0.1, "p_value": 0.6}))'
    result = run_analysis(ExperimentPlan(code=code), client=NullClient())
    assert result.supports_hypothesis is False


def test_run_analysis_broken_code_reports_failure():
    result = run_analysis(ExperimentPlan(code="raise RuntimeError('bad sim')"), client=NullClient())
    assert "failed" in result.summary.lower()
    assert result.supports_hypothesis is None


def test_run_analysis_codeless_offline_abstains():
    result = run_analysis(ExperimentPlan(), client=NullClient())
    assert result.supports_hypothesis is None
    assert "inconclusive" in result.summary


# ---------------------------------------------------------------------------
# critique_research
# ---------------------------------------------------------------------------


def test_critique_flags_structural_flaws_offline():
    bad_h = _good_hypothesis(falsification_test="")
    exp = ExperimentPlan(
        hypothesis_id=bad_h.id,
        variables=[Variable(name="x", kind="independent")],
        sample_size=4,
    )
    critique, needs_revision = critique_research("q", [bad_h], [exp], [], client=NullClient())
    assert needs_revision
    assert "not falsifiable" in critique
    assert "no controlled variables" in critique
    assert "never analysed" in critique
    assert "underpowered" in critique


def test_critique_flags_p_value_without_effect_size():
    exp = ExperimentPlan(variables=[Variable(name="c", kind="controlled")])
    analysis = AnalysisResult(experiment_id=exp.id, p_value=0.03)
    critique, needs_revision = critique_research(
        "q", [_good_hypothesis()], [exp], [analysis], client=NullClient()
    )
    assert needs_revision
    assert "without an effect size" in critique


def test_critique_clean_cycle_passes_offline():
    h = _good_hypothesis()
    exp = ExperimentPlan(
        hypothesis_id=h.id,
        variables=[Variable(name="c", kind="controlled")],
        sample_size=64,
    )
    analysis = AnalysisResult(experiment_id=exp.id, p_value=0.01, effect_size=0.5)
    critique, needs_revision = critique_research("q", [h], [exp], [analysis], client=NullClient())
    assert not needs_revision
    assert critique == "No structural flaws found."


def test_critique_llm_can_add_but_not_remove_findings(fake_client):
    client = fake_client(
        json.dumps(
            {
                "critique": "Confound: time of day.",
                "needs_revision": True,
                "fixes": ["Randomise session times."],
            }
        )
    )
    h = _good_hypothesis()
    exp = ExperimentPlan(
        hypothesis_id=h.id,
        variables=[Variable(name="c", kind="controlled")],
        sample_size=64,
    )
    analysis = AnalysisResult(experiment_id=exp.id, p_value=0.01, effect_size=0.5)
    critique, needs_revision = critique_research("q", [h], [exp], [analysis], client=client)
    assert needs_revision  # LLM verdict honoured even with clean structure
    assert "Confound: time of day." in critique
    assert "Randomise session times." in critique


# ---------------------------------------------------------------------------
# write_report / review_literature
# ---------------------------------------------------------------------------


def test_write_report_offline_sections_and_conclusion():
    h = _good_hypothesis(confidence=0.6)
    exp = ExperimentPlan(hypothesis_id=h.id, design="simulation")
    analysis = AnalysisResult(
        experiment_id=exp.id, summary="ran", p_value=0.01, effect_size=0.7, supports_hypothesis=True
    )
    report = write_report("q", [Paper(title="P1", year=2020)], [h], [exp], [analysis],
                          critique="minor", client=NullClient())
    assert "1 of 1 hypotheses were supported" in report.conclusion
    assert report.confidence == 0.6  # mean confidence of supported hypotheses
    for section in ("## Literature", "## Hypotheses", "## Experiments", "## Results",
                    "## Limitations", "## Conclusion", "## Open Questions"):
        assert section in report.report_markdown
    assert "P1" in report.report_markdown


def test_write_report_unsupported_hypotheses_stay_open():
    h = _good_hypothesis()
    report = write_report("q", [], [h], [], [], client=NullClient())
    assert "No hypothesis found support" in report.conclusion
    assert report.confidence == 0.0
    assert any(h.statement[:50] in q for q in report.open_questions)


def test_review_literature_offline_is_honest_about_no_retrieval():
    papers, synthesis = review_literature("spaced repetition", client=NullClient())
    assert papers == []  # network is blocked; _get degrades to None
    assert "No literature could be retrieved" in synthesis
