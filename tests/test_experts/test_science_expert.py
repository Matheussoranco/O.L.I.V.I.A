"""Science expert — symbolic STEM answers, routing, honest offline gaps."""

from __future__ import annotations

import importlib.util

import pytest

from olivia.experts import answer
from olivia.experts.router import get_experts, route
from olivia.experts.science_expert import ScienceExpert
from olivia.llm.client import NullClient

_HAS_SYMPY = importlib.util.find_spec("sympy") is not None


def test_science_expert_scores_stem_over_prose():
    expert = ScienceExpert()
    assert expert.score("what is the molar mass of H2SO4?") > expert.score("who wrote Hamlet?")
    assert expert.score("convert 5 km to miles") > 0.0


def test_science_expert_answers_molar_mass():
    result = ScienceExpert().answer("molar mass of glucose C6H12O6", client=NullClient())
    assert result.confidence == 0.95
    assert result.details["method"] == "chemistry"
    assert "180" in result.answer


def test_science_expert_converts_units():
    result = ScienceExpert().answer("convert 60 mph to m/s", client=NullClient())
    assert result.details["method"] == "units"
    assert "26.8224" in result.answer


def test_science_expert_looks_up_constants():
    result = ScienceExpert().answer("what is the Avogadro constant", client=NullClient())
    assert result.details["method"] == "physics"
    assert "6.02214076e+23" in result.answer or "6.022" in result.answer


def test_science_expert_honest_when_unsolvable_offline():
    result = ScienceExpert().answer("Why is the sky blue in poetic terms?", client=NullClient())
    assert result.confidence == 0.0
    assert "Cannot solve offline" in result.answer


def test_science_expert_registered_and_routes_chemistry():
    assert "science" in {e.name for e in get_experts()}
    ranked = {e.name: score for e, score in route("balance the equation H2 + O2 -> H2O")}
    assert ranked["science"] > ranked["general"]  # a genuine specialist here
    # End-to-end: whichever specialist ranks first, only science can actually
    # balance the equation, so the abstain-and-cascade lands there.
    result = answer("balance the equation H2 + O2 -> H2O", client=NullClient())
    assert result.expert == "science"
    assert "2 H2 + O2 -> 2 H2O" in result.answer


@pytest.mark.skipif(not _HAS_SYMPY, reason="sympy not installed")
def test_science_expert_defers_pure_math_ranking_to_math_expert():
    # Science can *solve* maths, but the math expert should out-rank it on maths.
    ranked = {e.name: score for e, score in route("integrate x**2")}
    assert ranked["math"] >= ranked["science"]
