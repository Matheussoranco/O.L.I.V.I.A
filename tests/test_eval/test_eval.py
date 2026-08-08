"""The eval harness — its scoring, its datasets' own invariants, and the gates.

Two jobs here. The first is ordinary: does the harness score correctly. The
second matters more — the *datasets* have honesty rules stated in their own
JSON ("every flawed case is structurally clean apart from its target flaw"),
and a rule nobody checks is a rule that quietly rots. Those are asserted here,
so the eval cannot drift into flattering itself.
"""

from __future__ import annotations

import importlib.util

import pytest

from olivia.eval import check_gates, load_dataset, load_gates, run_all, run_suite, suite_names
from olivia.eval.harness import CaseResult, EvalRun, Metric, SuiteReport, run_to_dict
from olivia.eval.sm2_reference import SM2State, replay, review, round_half_up
from olivia.eval.symbolic_eval import check_answer

_HAS_SYMPY = importlib.util.find_spec("sympy") is not None
_needs_sympy = pytest.mark.skipif(not _HAS_SYMPY, reason="sympy not installed")

_STRUCTURAL_FAMILIES = {"unfalsifiable_structural", "overfit_n1_structural"}
_MIN_SAMPLE = 10


# ---------------------------------------------------------------------------
# Answer checking
# ---------------------------------------------------------------------------


def test_numeric_check_reads_a_value_out_of_a_units_answer():
    check = {"kind": "numeric", "value": 98.072, "rtol": 0.01}
    assert check_answer(check, "98.08 g/mol")
    assert not check_answer(check, "18.02 g/mol")


def test_numeric_check_handles_fractions_and_scientific_notation():
    assert check_answer({"kind": "numeric", "value": 2.5, "rtol": 1e-9}, "5/2")
    assert check_answer({"kind": "numeric", "value": 6.02214076e23, "rtol": 1e-9}, "6.02214076e+23")


def test_an_empty_answer_is_never_correct():
    assert not check_answer({"kind": "numeric", "value": 0, "rtol": 1}, "")
    assert not check_answer({"kind": "contains", "values": ["x"]}, "   ")


def test_contains_check_is_case_insensitive_and_needs_every_value():
    check = {"kind": "contains", "values": ["2 H2 + O2", "2 H2O"]}
    assert check_answer(check, "2 h2 + o2 -> 2 h2o")
    assert not check_answer(check, "2 H2 + O2 -> H2O")


@_needs_sympy
def test_math_equal_ignores_form_and_the_integration_constant():
    assert check_answer({"kind": "math_equal", "expr": "x**2"}, "x**2 + C")
    assert check_answer({"kind": "math_equal", "expr": "cos(2*x)"}, "-sin(x)**2 + cos(x)**2")
    assert not check_answer({"kind": "math_equal", "expr": "2*x"}, "x**2")


@_needs_sympy
def test_roots_check_compares_sets_not_strings():
    check = {"kind": "roots", "values": ["2", "3"]}
    assert check_answer(check, "x = 3, x = 2")
    assert not check_answer(check, "x = 2")
    assert not check_answer(check, "x = 2, x = 4")


def test_unknown_check_kind_is_an_error_not_a_silent_pass():
    with pytest.raises(ValueError):
        check_answer({"kind": "vibes"}, "42")


# ---------------------------------------------------------------------------
# SM-2 reference
# ---------------------------------------------------------------------------


def test_round_half_up_differs_from_python_round_at_the_boundary():
    # The divergence the SM-2 suite reports: round() is half-to-even.
    assert round_half_up(552.5) == 553.0
    assert round(552.5) == 552


def test_reference_reproduces_the_published_first_three_intervals():
    first, second, third = replay([5, 5, 5])
    assert (first.interval_days, first.repetitions) == (1.0, 1)
    assert (second.interval_days, second.repetitions) == (6.0, 2)
    # I(3) = I(2) * EF, with EF as it stood before the third review's update.
    assert third.interval_days == round_half_up(6.0 * second.ease)


def test_reference_ease_matches_the_published_formula():
    # EF' = EF + (0.1 - (5-q)(0.08 + (5-q)0.02)); q=5 gives +0.1, q=4 gives 0.
    assert review(SM2State(), 5).ease == pytest.approx(2.6)
    assert review(SM2State(), 4).ease == pytest.approx(2.5)
    assert review(SM2State(), 3).ease == pytest.approx(2.36)


def test_reference_lapse_restarts_the_count_but_still_lowers_ease():
    lapsed = review(SM2State(ease=2.5, interval_days=90.0, repetitions=5), 1)
    assert (lapsed.repetitions, lapsed.interval_days) == (0, 1.0)
    assert lapsed.ease < 2.5


def test_reference_ease_never_falls_below_the_floor():
    assert replay([0] * 20)[-1].ease == pytest.approx(1.3)


def test_reference_rejects_out_of_range_quality():
    with pytest.raises(ValueError):
        review(SM2State(), 6)


# ---------------------------------------------------------------------------
# Dataset invariants — the eval's own honesty rules, machine-checked
# ---------------------------------------------------------------------------


def test_every_dataset_declares_how_it_was_held_out():
    for name in ("symbolic_solving", "research_critique", "sm2_sequences", "study_sources"):
        data = load_dataset(name)
        assert data.get("held_out", "").strip(), f"{name} must document its construction"


def test_case_ids_are_unique_within_every_dataset():
    for name, key in (
        ("symbolic_solving", "cases"),
        ("research_critique", "cases"),
        ("quiz_grading", "cases"),
        ("sm2_sequences", "sequences"),
        ("study_sources", "sources"),
    ):
        ids = [row["id"] for row in load_dataset(name)[key]]
        assert len(ids) == len(set(ids)), f"duplicate ids in {name}"


def test_flawed_research_cases_are_clean_apart_from_their_target_flaw():
    """The fairness rule the dataset states about itself.

    If a semantically flawed case also tripped a structural rule, a catch would
    look like epistemic insight when it was really the sample-size check. Only
    the two *_structural families are allowed to be structurally defective.
    """
    for case in load_dataset("research_critique")["cases"]:
        if case["label"] != "flawed" or case["family"] in _STRUCTURAL_FAMILIES:
            continue
        for hypothesis in case["hypotheses"]:
            assert hypothesis["predictions"], f"{case['id']}: predictions missing"
            assert hypothesis["falsification_test"].strip(), f"{case['id']}: no refutation test"
        for experiment in case["experiments"]:
            kinds = {v["kind"] for v in experiment["variables"]}
            assert "controlled" in kinds, f"{case['id']}: no controlled variable"
            assert experiment["sample_size"] >= _MIN_SAMPLE, f"{case['id']}: underpowered"
            analysed = {a["experiment_id"] for a in case["analyses"]}
            assert experiment["id"] in analysed, f"{case['id']}: experiment never analysed"
        for analysis in case["analyses"]:
            if analysis.get("p_value") is not None:
                assert analysis.get("effect_size") is not None, f"{case['id']}: p without effect"


def test_sound_control_cases_are_structurally_impeccable():
    for case in load_dataset("research_critique")["cases"]:
        if case["label"] != "sound":
            continue
        for experiment in case["experiments"]:
            assert experiment["sample_size"] >= 30, f"{case['id']}: control is underpowered"
        for analysis in case["analyses"]:
            assert analysis.get("effect_size") is not None
            assert analysis.get("ci_low") is not None, f"{case['id']}: control lacks an interval"


def test_the_critique_set_has_both_flawed_cases_and_controls():
    labels = [c["label"] for c in load_dataset("research_critique")["cases"]]
    assert labels.count("flawed") >= 15
    assert labels.count("sound") >= 5, "without controls a false-alarm rate is unmeasurable"


def test_the_symbolic_set_spans_both_tiers_and_every_domain():
    cases = load_dataset("symbolic_solving")["cases"]
    tiers = {c["tier"] for c in cases}
    domains = {c["domain"] for c in cases}
    assert tiers == {"core", "reach"}
    assert domains == {"math", "chemistry", "physics", "units"}
    reach = [c for c in cases if c["tier"] == "reach"]
    assert len(reach) >= 20, "a set that only tests what already works measures nothing"


def test_sm2_sequences_exercise_the_lapse_path():
    sequences = load_dataset("sm2_sequences")["sequences"]
    lapses = sum(1 for s in sequences for q in s["grades"] if q < 3)
    assert lapses >= 20, "the relearning branch must be scored, not assumed"


# ---------------------------------------------------------------------------
# Metric semantics
# ---------------------------------------------------------------------------


def _fake_research_run(flag_everything: bool) -> list[CaseResult]:
    from olivia.eval.research_eval import _decision_metrics

    cases = [
        CaseResult(
            id=f"c{i}",
            outcome="correct",
            group="fake",
            meta={"label": label, "flagged": flag_everything},
        )
        for i, label in enumerate(["flawed"] * 6 + ["sound"] * 4)
    ]
    return _decision_metrics(cases, "test.")


def test_a_critic_that_flags_everything_scores_zero_on_youden_j():
    metrics = {m.name: m.value for m in _fake_research_run(flag_everything=True)}
    assert metrics["test.catch_rate"] == 1.0
    assert metrics["test.false_alarm_rate"] == 1.0
    assert metrics["test.youden_j"] == 0.0
    assert metrics["test.balanced_accuracy"] == 0.5


def test_a_critic_that_flags_nothing_also_scores_zero_on_youden_j():
    metrics = {m.name: m.value for m in _fake_research_run(flag_everything=False)}
    assert metrics["test.catch_rate"] == 0.0
    assert metrics["test.false_alarm_rate"] == 0.0
    assert metrics["test.youden_j"] == 0.0
    assert metrics["test.balanced_accuracy"] == 0.5


# ---------------------------------------------------------------------------
# Suites and gates
# ---------------------------------------------------------------------------


def test_every_suite_is_registered():
    assert set(suite_names()) == {"symbolic", "research", "study"}


@pytest.mark.parametrize("name", ["symbolic", "research", "study"])
def test_each_suite_runs_offline_and_produces_metrics(name):
    report = run_suite(name, client=None)
    assert report.metrics, f"{name} produced no metrics"
    assert report.cases, f"{name} scored no cases"
    assert all(0.0 <= m.value <= 1.0 for m in report.metrics)


def test_llm_dependent_paths_report_skipped_rather_than_failing():
    run = run_all(client=None)
    assert run.llm_backend == "none"
    flat = run.flat_metrics()
    assert flat["symbolic.fallback.measured"] == 0.0
    assert flat["research.llm.measured"] == 0.0
    assert flat["study.generation.llm_measured"] == 0.0


def test_the_recorded_gates_still_hold():
    """The regression ratchet: this is what CI is really running."""
    assert check_gates(run_all(client=None)) == []


def test_gates_are_declared_in_both_directions():
    gates = load_gates()
    assert gates["floors"], "no floors recorded"
    # Rates where lower is better must be ceilings, never floors.
    assert "symbolic.symbolic.wrong_rate" in gates["ceilings"]
    assert "research.symbolic.false_alarm_rate" in gates["ceilings"]
    assert not any(k.endswith("wrong_rate") for k in gates["floors"])


def test_a_breached_floor_is_reported():
    run = EvalRun(reports=[SuiteReport(suite="s", metrics=[Metric("m", 0.4, 10)])])
    assert check_gates(run, {"floors": {"s.m": 0.9}, "ceilings": {}}) == [
        "s.m: 0.4000 < floor 0.9000"
    ]


def test_a_breached_ceiling_is_reported():
    run = EvalRun(reports=[SuiteReport(suite="s", metrics=[Metric("m", 0.4, 10)])])
    assert check_gates(run, {"floors": {}, "ceilings": {"s.m": 0.1}}) == [
        "s.m: 0.4000 > ceiling 0.1000"
    ]


def test_a_gate_on_a_skipped_suite_is_not_a_failure():
    run = EvalRun(reports=[SuiteReport(suite="s", skipped=True, skip_reason="no key")])
    assert check_gates(run, {"floors": {"s.m": 0.9}, "ceilings": {}}) == []


def test_results_serialise_to_plain_json():
    import json

    payload = run_to_dict(run_all(client=None, suites=["study"]))
    assert json.loads(json.dumps(payload, default=str))["metrics"]
