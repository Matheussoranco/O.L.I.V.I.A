"""Solver parse failures surface as typed errors, never silent "no match".

Regression tests for the ``except Exception: return None`` cleanup: every
maths branch parses via ``safe_sympify`` and raises ``SolverParseError`` (an
``OliviaError``) when a matched intent carries a broken expression, so
``solve_problem`` can log the failure instead of mistaking it for "no match".
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from olivia.core.errors import OliviaError, SolverParseError
from olivia.llm.client import NullClient
from olivia.study.equations import check_expression_growth
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


@pytest.mark.parametrize(
    ("problem", "expected"),
    [
        ("what is 2^10 + 1", "1025"),
        ("calculate 2^(3^2) + 1", "513"),
        ("what is 2**10 - 24", "1000"),
    ],
)
def test_bounded_arithmetic_powers_still_evaluate(problem, expected):
    pytest.importorskip("sympy")
    sol = solve_problem(problem, client=NullClient())
    assert sol.method == "symbolic"
    assert sol.final_answer == expected


def test_check_expression_growth_rejects_explosive_power_and_allows_bounded():
    pytest.importorskip("sympy")
    check_expression_growth("2**10 + 1")
    with pytest.raises(SolverParseError, match="exceeds"):
        check_expression_growth("9**9**9 * 2")


_EXPLOSIVE_NON_EQUATION_PROBLEMS = [
    "calculate 9^9^9 * 2",
    "what is 2^999999999 + 1",
    "what is 2^(((999999999))) + 1",
    "what is 2^2^2^2^2 + 1",
    "calculate 2**999999999",
    "calculate " + " * ".join(["(10^500)"] * 9),  # > 4300-digit int->str defence in depth
    "simplify 9^9^9",
    "simplify Pow(2, 999999999)",
    "simplify factorial(100000)",
    "simplify 1 << 1000000",
    "differentiate 9^9^9 * x",
    "expand (x + 1)^100000",
    "find the roots of x^1000000 - 1",
]

_EXPLOSIVE_CHILD = """
import sys, time
from olivia.core.errors import SolverParseError
from olivia.llm.client import NullClient
from olivia.study.solver import _solve_math, solve_problem

for problem in sys.argv[1:]:
    started = time.perf_counter()
    try:
        _solve_math(problem)
        direct = "NOT-REFUSED"
    except SolverParseError:
        direct = "refused"
    except Exception as exc:
        direct = "ESCAPED-" + type(exc).__name__
    sol = solve_problem(problem, client=NullClient())
    elapsed = time.perf_counter() - started
    print(f"{direct}\\t{sol.method}\\t{elapsed:.3f}\\t{problem}", flush=True)
"""


def test_explosive_arithmetic_and_symbolic_paths_refused_fast():
    """Issue #24: arithmetic and non-equation symbolic paths must not hang sympy."""
    pytest.importorskip("sympy")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    try:
        child = subprocess.run(
            [sys.executable, "-c", _EXPLOSIVE_CHILD, *_EXPLOSIVE_NON_EQUATION_PROBLEMS],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        done = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else exc.stdout
        pytest.fail(f"hung after:\n{done}")

    rows = [line.split("\t") for line in child.stdout.splitlines() if line.strip()]
    assert len(rows) == len(_EXPLOSIVE_NON_EQUATION_PROBLEMS), child.stderr[-2000:]
    for direct, method, seconds, problem in rows:
        assert direct == "refused", f"{problem}: direct={direct}"
        assert method == "none", f"{problem}: method={method}"
        assert float(seconds) < 2.0, f"{problem}: took {seconds}s"


def test_explosive_arithmetic_logs_warning_and_abstains(caplog):
    pytest.importorskip("sympy")
    with caplog.at_level("WARNING", logger="olivia.study.solver"):
        sol = solve_problem("calculate 9^9^9 * 2", client=NullClient())
    assert sol.method == "none"
    assert sol.confidence == 0.0
    assert any("parse error" in rec.message for rec in caplog.records)


@pytest.mark.parametrize(
    ("problem", "expected_substring"),
    [
        ("differentiate x^100", "100*x**99"),
        ("derivative of x^1000", "1000*x**999"),
        ("integrate x^100", "x**101/101 + C"),
        ("expand (x+1)^100", "x**100"),
        ("factor x^100 - 1", "(x - 1)"),
        ("simplify x^100/x^98", "x**2"),
    ],
)
def test_large_symbolic_exponents_preserved_on_non_solve_paths(
    problem: str, expected_substring: str
):
    """Review regression (B1): unknown-degree solve cap must not break diff/integrate/etc."""
    pytest.importorskip("sympy")
    sol = solve_problem(problem, client=NullClient())
    assert sol.method == "symbolic"
    assert expected_substring in sol.final_answer


def test_symbolic_math_tool_refuses_explosive_expressions_fast():
    """Shared safe_sympify guard also protects tools.science.symbolic_math (MCP/experts)."""
    pytest.importorskip("sympy")
    probe = (
        "import time\n"
        "from olivia.tools.science import symbolic_math\n"
        "for expr in ('9^9^9 * 2', '2^999999999 + 1', 'Pow(2, 999999999)', 'factorial(100000)'):\n"
        "    t0 = time.perf_counter()\n"
        "    out = symbolic_math(expr, 'simplify')\n"
        "    dt = time.perf_counter() - t0\n"
        "    assert out.startswith('error:'), (expr, out)\n"
        "    assert dt < 2.0, (expr, dt)\n"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
