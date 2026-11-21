"""T4 (#12): the equation parser — systems and notation variants.

Covers the acceptance criteria end-to-end through the real ``olivia solve``
command, then the parser's contract piece by piece: notation, splitting, the
prose guard (which stops "the value 2x = 4" being "solved" as a product of
letters), worked steps, degenerate systems and resource bounds.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import time

import pytest

pytest.importorskip("sympy")

from typer.testing import CliRunner

from olivia.__main__ import app
from olivia.core.errors import SolverParseError
from olivia.llm.client import NullClient
from olivia.study.equations import (
    MAX_EQUATIONS,
    normalise_notation,
    parse_equations,
    solve_equations,
)
from olivia.study.solver import solve_problem


def _solve(problem: str):
    return solve_problem(problem, client=NullClient())


# ---------------------------------------------------------------------------
# Acceptance criteria (issue #12), through the CLI
# ---------------------------------------------------------------------------


@pytest.fixture
def offline(monkeypatch):
    """Force the null backend so the CLI cannot reach a real LLM."""
    monkeypatch.setattr("olivia.study.solver.get_client", lambda *a, **k: NullClient())


@pytest.mark.parametrize(
    ("problem", "answer"),
    [
        ("the system 2x + y = 10 and x - y = 2", "x = 4, y = 2"),
        ("solve 2x + y = 10, x - y = 2", "x = 4, y = 2"),
        ("x^2 - 5x + 6 = 0", "x = 2, x = 3"),
        ("2*x + 3 = 7", "x = 2"),
    ],
)
def test_acceptance_via_olivia_solve_cli(offline, problem, answer):
    result = CliRunner().invoke(app, ["solve", problem])
    assert result.exit_code == 0, result.output
    assert f"Answer: {answer}" in result.output
    assert "computed symbolically" in result.output


def test_acceptance_system_shows_worked_steps():
    sol = _solve("the system 2x + y = 10 and x - y = 2")
    descriptions = [step.description for step in sol.steps]
    assert sol.final_answer == "x = 4, y = 2"
    assert descriptions[0] == "Restate the system"
    assert any(d.startswith("Eliminate x from equation 2") for d in descriptions)
    assert sol.steps[-1].result == "every equation holds"
    assert sol.confidence == 0.9


# ---------------------------------------------------------------------------
# Notation variants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "normalised"),
    [
        ("x² − 5x + 6 = 0", "x^2 - 5x + 6 = 0"),
        ("x⁻¹ = 2", "x^(-1) = 2"),
        ("2×x ÷ 4 = 1", "2*x / 4 = 1"),
        ("3·a⋅b = 6", "3*a*b = 6"),
        ("√x = 3", "sqrt(x) = 3"),
        ("√(x + 1) = 3", "sqrt(x + 1) = 3"),
        ("2πr = 1", "2 pi r = 1"),
        ("x == 2", "x = 2"),
        ("x + 1 ＝ 2", "x + 1 = 2"),
    ],
)
def test_normalise_notation(raw, normalised):
    assert normalise_notation(raw) == normalised


@pytest.mark.parametrize(
    ("problem", "answer"),
    [
        ("x² − 5x + 6 = 0", "x = 2, x = 3"),
        ("2×x + 3 = 7", "x = 2"),
        ("solve x**2 = 4", "x = -2, x = 2"),
        ("solve √x = 3", "x = 9"),
        ("solve 2(x + 1) = 6", "x = 2"),
        ("solve x == 5", "x = 5"),
        ("Solve the equation 3x - 4 = 11.", "x = 5"),
        ("solve for x: 3x + 2 = 11", "x = 3"),
        ("{2x + y = 10; x - y = 2}", "x = 4, y = 2"),
        ("solve 2x + y = 10; x - y = 2", "x = 4, y = 2"),
        ("solve 2x + y = 10\nx - y = 2", "x = 4, y = 2"),
        ("Solve the system of linear equations: 3a - b = 5, a + b = 3.", "a = 2, b = 1"),
        ("solve for x and y: 2x + y = 10, x - y = 2", "x = 4, y = 2"),
        ("solve 2x + y = 10, x - y = 2 for x, y", "x = 4, y = 2"),
        ("solve x1 + x2 = 3 and x1 - x2 = 1", "x_1 = 2, x_2 = 1"),
        ("solve log(x, 2) = 3", "x = 8"),
        ("solve xy = 6 and x + y = 5", "x = 2, y = 3; x = 3, y = 2"),
    ],
)
def test_notation_variants_solve(problem, answer):
    sol = _solve(problem)
    assert sol.method == "symbolic", sol.steps[0].description
    assert sol.final_answer == answer


def test_digit_glued_to_name_is_a_product_not_a_python_literal():
    # Python lexes 0x as a hex prefix and 3j as the complex number 3i.
    assert _solve("solve 0x + y = 1 and x + 0y = 2").final_answer == "x = 2, y = 1"
    assert _solve("solve 3j = 6").final_answer == "j = 2"


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------


def test_commas_inside_brackets_do_not_split():
    parsed = parse_equations("solve log(x, 2) = 3")
    assert parsed is not None
    assert len(parsed.equations) == 1


def test_three_equations_with_mixed_separators():
    parsed = parse_equations("solve x + y + z = 6, 2x - y + z = 3 and x + 2y - z = 2")
    assert parsed is not None
    assert [str(eq) for eq in parsed.equations] == [
        "x + y + z = 6",
        "2x - y + z = 3",
        "x + 2y - z = 2",
    ]


def test_trailing_unknowns_are_captured():
    parsed = parse_equations("solve v = u + a*t for t")
    assert parsed is not None and parsed.unknowns == ("t",)
    assert parsed.explicit


# ---------------------------------------------------------------------------
# The prose guard: words are not products of single-letter symbols
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "the value 2x = 4",  # main used to answer x = 2*exp(-2)/(a*h*l*t*u*v)
        "Evaluate 2x + 3 = 7",
        "balance H2 + O2 = H2O",
        "If f(x) = 3x^2 + 2x, what is f'(x)?",
        "x < 3",
        "x >= 3 = y",
    ],
)
def test_non_equation_text_is_not_claimed(text):
    assert parse_equations(text) is None


def test_explicit_instruction_with_prose_is_a_typed_error():
    with pytest.raises(SolverParseError):
        parse_equations("solve x + y = 3 and the answer")
    with pytest.raises(SolverParseError):
        parse_equations("solve the value 2x = 4")


def test_prose_offline_abstains_instead_of_guessing():
    sol = _solve("the value 2x = 4")
    assert sol.method == "none"
    assert sol.confidence == 0.0


def test_other_solvers_still_own_their_inputs():
    assert _solve("balance H2 + O2 = H2O").method == "chemistry"
    assert _solve("If f(x) = 3x^2 + 2x, what is f'(x)?").final_answer == "6*x + 2"


# ---------------------------------------------------------------------------
# Worked steps and degenerate cases
# ---------------------------------------------------------------------------


def test_three_by_three_elimination_steps():
    sol = _solve("solve x + y + z = 6, 2x - y + z = 3, x + 2y - z = 2")
    descriptions = [step.description for step in sol.steps]
    assert sol.final_answer == "x = 1, y = 2, z = 3"
    assert sum(d.startswith("Eliminate") for d in descriptions) == 3
    assert descriptions.count("Back-substitute for y") == 1
    assert "Solve the last equation for z" in descriptions


def test_zero_pivot_triggers_a_row_swap():
    sol = _solve("solve 0x + y = 1 and x + y = 3")
    assert sol.final_answer == "x = 2, y = 1"
    assert any(step.description == "Swap equations 1 and 2" for step in sol.steps)


def test_inconsistent_system_explains_why():
    sol = _solve("solve x + y + z = 6, x - y = 0, 2x + z = 5")
    assert sol.final_answer == "no solution"
    assert any("determinant is 0" in step.description for step in sol.steps)


def test_dependent_system_names_the_free_parameter():
    sol = _solve("solve x + y = 2 and 2x + 2y = 4")
    assert sol.final_answer == "x = 2 - y"  # unchanged contract (see test_solver.py)
    assert any("y is a free parameter" in step.result for step in sol.steps)
    assert sol.steps[-1].result == "every equation holds"


def test_parameters_are_not_mistaken_for_unknowns():
    sol = _solve("solve x + y = a and x - y = b")
    assert sol.final_answer == "x = a/2 + b/2, y = a/2 - b/2"


@pytest.mark.parametrize(
    ("problem", "answer"),
    [
        ("solve x + 1 = x + 1", "every value is a solution (identity)"),
        ("solve x + 1 = x + 2", "no solution"),  # main answered "no solution" to both
    ],
)
def test_identity_and_contradiction(problem, answer):
    assert _solve(problem).final_answer == answer


def test_requested_unknown_is_honoured():
    # Without "for t", alphabetical choice would solve for a.
    assert _solve("solve v = u + a*t for t").final_answer == "t = (-u + v)/a"


def test_requested_unknown_absent_from_equation_is_an_error():
    with pytest.raises(SolverParseError, match="does not appear"):
        solve_equations("solve 2x = 4 for y")


@pytest.mark.parametrize(
    ("problem", "kind"),
    [
        ("x^2 - 5x + 6 = 0", "two distinct real roots"),
        ("x^2 + 2x + 1 = 0", "one repeated root"),
        ("x^2 + 1 = 0", "two complex conjugate roots"),
    ],
)
def test_quadratic_discriminant_step(problem, kind):
    sol = _solve(problem)
    assert any(
        step.description.startswith("Discriminant") and kind in step.result for step in sol.steps
    )


def test_steps_render_caret_powers_but_answer_keeps_sympy_form():
    sol = _solve("solve x^2 - 4 = 0")
    assert all("**" not in step.result for step in sol.steps)
    assert sol.final_answer == "x = -2, x = 2"


# ---------------------------------------------------------------------------
# Resource bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "problem", ["solve x^1000000 = 1", "solve 2^999999999 = x", "solve x**(-99999) = 1"]
)
def test_huge_exponents_are_refused_before_sympy(problem):
    started = time.perf_counter()
    with pytest.raises(SolverParseError, match="exceeds"):
        solve_equations(problem)
    assert time.perf_counter() - started < 1.0


def test_computed_huge_power_is_refused():
    with pytest.raises(SolverParseError, match="exceeds"):
        solve_equations("solve x^(8*8*8) = 1")


# Review of PR #22 (Gemini, 36e0eb3): the token lookahead could be blinded by
# parentheses, and power towers whose every literal is small still explode,
# because sympy evaluates Integer**Integer the moment the text is parsed.
_EXPLOSIVE = [
    "solve 2^(((999999999))) = x",  # parens exhausted the 3-token lookahead
    "solve 2^(-(-(999999999))) = x",
    "solve 2^3^20 = x",  # right-associative: 2^(3^20), 3.5e9 exponent
    "solve 2^2^2^2^2 = x",  # 2^65536: computes, then str() overflowed
    "solve x = (10^10)^(10^10)",
    "solve 9**9**9 = x",
    "solve x = 2^(64*64*64)",  # every literal small, product huge
    "solve x = factorial(10^6)",  # eager combinatorial evaluation
    "solve x = fibonacci(10^9)",
]
_CHILD = """
import sys, time
from olivia.core.errors import SolverParseError
from olivia.study.equations import solve_equations
for problem in sys.argv[1:]:
    started = time.perf_counter()
    try:
        solve_equations(problem)
        outcome = "NOT-REFUSED"
    except SolverParseError:
        outcome = "refused"
    except Exception as exc:  # anything else escaping is a contract break
        outcome = "ESCAPED-" + type(exc).__name__
    print(f"{outcome}\\t{time.perf_counter() - started:.3f}\\t{problem}", flush=True)
"""


def test_explosive_numeric_powers_are_refused_before_evaluation():
    # A child process with a hard timeout: if this guard ever regresses, the
    # suite fails in seconds instead of hanging CI inside sympy.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    try:
        child = subprocess.run(
            [sys.executable, "-c", _CHILD, *_EXPLOSIVE],
            capture_output=True,
            text=True,
            timeout=90,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        done = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else exc.stdout
        pytest.fail(f"hung after:\n{done}")
    rows = [line.split("\t") for line in child.stdout.splitlines() if line.strip()]
    assert len(rows) == len(_EXPLOSIVE), child.stderr[-2000:]
    for outcome, seconds, problem in rows:
        assert outcome == "refused", problem
        assert float(seconds) < 2.0, problem


@pytest.mark.parametrize(
    ("problem", "answer"),
    [
        ("solve x = 2^10", "x = 1024"),
        ("solve x = 2^(3^2)", "x = 512"),  # a small tower is still fine
        ("solve 2^x = 1024", "x = 10"),  # symbolic exponent: nothing to bound
        ("solve x = factorial(5)", "x = 120"),
        ("solve x^(1/2) = 3", "x = 9"),
        ("solve x = 10^(-3)", "x = 1/1000"),
    ],
)
def test_bounded_powers_still_solve(problem, answer):
    assert _solve(problem).final_answer == answer


def test_bare_explosive_power_is_left_alone_not_raised():
    # Without an instruction the text is simply not claimed (contract: None).
    assert parse_equations("2^3^20 = x") is None


def test_single_equation_with_several_requested_unknowns_keeps_them():
    # Review NB1: "for x and y" on one equation used to drop y silently.
    sol = _solve("solve x + y = 5 for x and y")
    assert sol.final_answer == "x = 5 - y"
    assert any("y is a free parameter" in step.result for step in sol.steps)


def test_identity_still_validates_requested_unknown():
    # Review NB2: consistent with "solve 2x = 4 for y".
    with pytest.raises(SolverParseError, match="does not appear"):
        solve_equations("solve x + 1 = x + 1 for y")
    assert (
        _solve("solve x + 1 = x + 1 for x").final_answer == "every value is a solution (identity)"
    )


def test_too_many_equations_is_refused():
    system = ", ".join(f"x + {i} = y" for i in range(MAX_EQUATIONS + 1))
    with pytest.raises(SolverParseError, match="more than"):
        parse_equations(f"solve {system}")


# ---------------------------------------------------------------------------
# Generated systems: the parser and elimination agree with the construction
# ---------------------------------------------------------------------------


def _term(coeff: int, name: str, first: bool, style: str) -> str:
    if coeff == 0:
        return ""
    sign = "-" if coeff < 0 else ("" if first else "+")
    minus = {"unicode": "−"}.get(style, "-") if sign == "-" else sign
    magnitude = abs(coeff)
    times = {"explicit": "*", "unicode": "×"}.get(style, "")
    body = name if magnitude == 1 else f"{magnitude}{times}{name}"
    return f"{minus} {body}".strip() if not first else f"{minus}{body}"


@pytest.mark.parametrize("seed", range(40))
def test_generated_square_systems(seed):
    import sympy

    rng = random.Random(seed)
    n = rng.choice([2, 3])
    names = ["x", "y", "z"][:n]
    style = rng.choice(["implicit", "explicit", "unicode"])
    while True:
        matrix = sympy.Matrix(n, n, lambda *_: rng.randint(-5, 5))
        if matrix.det() != 0:
            break
    solution = [rng.randint(-9, 9) for _ in range(n)]
    rhs = matrix * sympy.Matrix(solution)
    equations = []
    for r in range(n):
        terms = [t for c in range(n) if (t := _term(matrix[r, c], names[c], c == 0, style))]
        lhs = " ".join(terms) if terms else "0"
        equations.append(f"{lhs} = {rhs[r]}")
    separator = rng.choice([", ", "; ", " and "])
    problem = f"solve {separator.join(equations)}"

    sol = _solve(problem)

    expected = ", ".join(f"{name} = {value}" for name, value in zip(names, solution, strict=True))
    assert sol.final_answer == expected, problem
    assert sol.steps[-1].result == "every equation holds", problem
    assert any(step.description.startswith("Back-substitute") for step in sol.steps), problem
