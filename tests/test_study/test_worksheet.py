"""Practice worksheets — seeded offline generation, solved answer keys."""

from __future__ import annotations

import importlib.util

import pytest

from olivia.llm.client import NullClient
from olivia.study.worksheet import generate_worksheet, worksheet_to_markdown

_HAS_SYMPY = importlib.util.find_spec("sympy") is not None
_needs_sympy = pytest.mark.skipif(not _HAS_SYMPY, reason="sympy not installed")


@_needs_sympy
def test_offline_linear_worksheet_is_solved():
    sheet = generate_worksheet("linear equations", n=4, seed=7, client=NullClient())
    assert len(sheet) == 4
    assert all(sol.method == "symbolic" for sol in sheet)
    assert all(sol.final_answer for sol in sheet)
    assert all(sol.problem.startswith("solve") for sol in sheet)


@_needs_sympy
def test_offline_generation_is_deterministic_with_seed():
    a = generate_worksheet("quadratics", n=3, seed=99, client=NullClient())
    b = generate_worksheet("quadratics", n=3, seed=99, client=NullClient())
    assert [s.problem for s in a] == [s.problem for s in b]


def test_non_math_topic_degrades_to_empty_offline():
    assert generate_worksheet("the French Revolution", n=3, client=NullClient()) == []


@_needs_sympy
def test_worksheet_markdown_has_problems_and_answer_key():
    sheet = generate_worksheet("derivatives", n=2, seed=3, client=NullClient())
    md = worksheet_to_markdown(sheet, topic="derivatives")
    assert "# Worksheet: derivatives" in md
    assert "## Answer key" in md
    assert md.count("**Answer:**") == 2
