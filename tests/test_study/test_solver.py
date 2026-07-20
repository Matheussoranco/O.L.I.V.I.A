"""Step-by-step solver — symbolic maths, science tools, honest offline gaps."""

from __future__ import annotations

import importlib.util

import pytest

from olivia.core.records import WorkedSolution
from olivia.llm.client import NullClient
from olivia.study.solver import solution_to_markdown, solve_problem

_HAS_SYMPY = importlib.util.find_spec("sympy") is not None
_needs_sympy = pytest.mark.skipif(not _HAS_SYMPY, reason="sympy not installed")


@_needs_sympy
def test_solve_quadratic_shows_work():
    sol = solve_problem("solve x**2 - 5*x + 6 = 0 for x", client=NullClient())
    assert sol.method == "symbolic"
    assert sol.confidence == 0.9
    assert "x = 2" in sol.final_answer and "x = 3" in sol.final_answer
    descriptions = " ".join(s.description.lower() for s in sol.steps)
    assert "factor" in descriptions  # the factoring step appears for a factorable poly
    assert len(sol.steps) >= 3


@_needs_sympy
def test_solve_derivative_and_integral():
    deriv = solve_problem("differentiate x**3 + 2*x", client=NullClient())
    assert deriv.method == "symbolic"
    assert "3*x**2 + 2" in deriv.final_answer
    integral = solve_problem("integrate 2*x", client=NullClient())
    assert "x**2" in integral.final_answer and "+ C" in integral.final_answer


@_needs_sympy
def test_evaluate_arithmetic_is_exact():
    assert solve_problem("what is 12 * 8 + 5", client=NullClient()).final_answer == "101"
    assert solve_problem("what is 10/4", client=NullClient()).final_answer == "5/2"


def test_chemistry_molar_mass_route():
    sol = solve_problem("molar mass of H2SO4", client=NullClient())
    assert sol.method == "chemistry"
    assert sol.confidence == 0.95
    assert "98" in sol.final_answer
    assert sol.steps  # one line per element plus the total


def test_chemistry_balance_route():
    sol = solve_problem("balance H2 + O2 -> H2O", client=NullClient())
    assert sol.method == "chemistry"
    assert sol.final_answer == "2 H2 + O2 -> 2 H2O"


def test_physics_constant_route():
    sol = solve_problem("what is the speed of light", client=NullClient())
    assert sol.method == "physics"
    assert "299792458" in sol.final_answer


def test_units_conversion_route():
    sol = solve_problem("convert 60 mph to m/s", client=NullClient())
    assert sol.method == "units"
    assert "26.8224" in sol.final_answer


def test_unsolvable_offline_is_honest():
    sol = solve_problem("Discuss the causes of the French Revolution.", client=NullClient())
    assert sol.method == "none"
    assert sol.confidence == 0.0
    assert sol.final_answer == ""
    assert "cannot be solved offline" in sol.steps[0].description


def test_forced_subject_skips_other_solvers():
    # A chemistry problem forced to 'math' finds no maths and, offline, abstains.
    sol = solve_problem("molar mass of H2O", subject="math", client=NullClient())
    assert sol.method == "none"


@_needs_sympy
def test_solution_to_markdown_renders_steps_and_answer():
    md = solution_to_markdown(solve_problem("solve 2*x = 8 for x", client=NullClient()))
    assert "**Problem:**" in md
    assert "**Answer:** x = 4" in md
    assert "Method: computed symbolically" in md


def test_solve_returns_worked_solution_type():
    assert isinstance(solve_problem("molar mass of O2", client=NullClient()), WorkedSolution)
