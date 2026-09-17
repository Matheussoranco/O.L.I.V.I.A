"""Solver parse failures surface as typed errors, never silent "no match".

Regression tests for the ``except Exception: return None`` cleanup: every
maths branch parses via ``safe_sympify`` and raises ``SolverParseError`` (an
``OliviaError``) when a matched intent carries a broken expression, so
``solve_problem`` can log the failure instead of mistaking it for "no match".
"""

from __future__ import annotations

import pytest

from olivia.core.errors import OliviaError, SolverParseError
from olivia.llm.client import NullClient
from olivia.study.solver import _evaluate_arithmetic, _solve_math, solve_problem


def test_solve_parse_error_is_typed_and_carries_expression():
    with pytest.raises(SolverParseError) as exc_info:
        _solve_math("solve @@@ = 0 for x")
    assert isinstance(exc_info.value, OliviaError)
    assert exc_info.value.expression  # the offending expression travels with the error


@pytest.mark.parametrize(
    "problem",
    [
        "differentiate @@@",
        "integrate @@@",
        "simplify @@@",
        "factor @@@",
        "expand @@@",
    ],
)
def test_other_math_branches_raise_typed_errors(problem):
    with pytest.raises(SolverParseError):
        _solve_math(problem)


def test_dunder_expression_blocked_by_policy():
    with pytest.raises(SolverParseError):
        _solve_math("solve __import__('os') = 0 for x")


@pytest.mark.parametrize("problem", ["what is 2 +* 3", "what is (2+3"])
def test_broken_arithmetic_raises_typed_error(problem):
    with pytest.raises(SolverParseError):
        _evaluate_arithmetic(problem, problem)


def test_broken_expression_offline_is_honest_not_silent(caplog):
    with caplog.at_level("WARNING", logger="olivia.study.solver"):
        sol = solve_problem("solve @@@ = 0 for x", client=NullClient())
    assert sol.method == "none"  # surfaced parse failure, then honest abstention
    assert sol.confidence == 0.0
    assert any("parse error" in rec.message for rec in caplog.records)


def test_arithmetic_still_evaluates_via_safe_sympify():
    sol = solve_problem("calculate (2+3)*4", client=NullClient())
    assert sol.method == "symbolic"
    assert sol.final_answer == "20"
