"""Scientific computation tools — sandboxed Python, symbolic math, statistics.

Statistics run on the standard library (``statistics.NormalDist``); scipy and
sympy upgrade precision when installed but are never required.  ``python_exec``
runs code in an isolated subprocess (``-I``) with a hard timeout — it is the
execution backend for experiment simulations designed by the research cycle.
"""

from __future__ import annotations

import logging
import math
import statistics
import subprocess
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from olivia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sandboxed execution
# ---------------------------------------------------------------------------


def python_exec(code: str, timeout: float = 30.0) -> dict[str, Any]:
    """Run Python code in an isolated subprocess; return {ok, stdout, stderr}."""
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout[-20000:],
            "stderr": proc.stderr[-4000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"timeout after {timeout}s"}
    except Exception as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc)}


# ---------------------------------------------------------------------------
# Symbolic math (sympy optional)
# ---------------------------------------------------------------------------

_OPERATIONS = ("simplify", "expand", "factor", "solve", "diff", "integrate")


def symbolic_math(expression: str, operation: str = "simplify", variable: str = "x") -> str:
    """Apply a sympy operation to an expression; explain if sympy is missing."""
    if operation not in _OPERATIONS:
        return f"error: unknown operation '{operation}' (use one of {', '.join(_OPERATIONS)})"
    try:
        import sympy
    except ImportError:
        return "error: sympy not installed (pip install olivia[science])"
    try:
        symbol = sympy.Symbol(variable)
        expr = sympy.sympify(expression)
        if operation == "solve":
            return str(sympy.solve(expr, symbol))
        if operation == "diff":
            return str(sympy.diff(expr, symbol))
        if operation == "integrate":
            return str(sympy.integrate(expr, symbol))
        return str(getattr(sympy, operation)(expr))
    except Exception as exc:
        return f"error: {exc}"


# ---------------------------------------------------------------------------
# Statistics (stdlib core, scipy refinement)
# ---------------------------------------------------------------------------


def stats_summary(data: list[float]) -> dict[str, float]:
    """Descriptive statistics for one sample."""
    if not data:
        return {"n": 0}
    summary: dict[str, float] = {
        "n": len(data),
        "mean": statistics.fmean(data),
        "median": statistics.median(data),
        "min": min(data),
        "max": max(data),
    }
    if len(data) >= 2:
        summary["stdev"] = statistics.stdev(data)
        summary["sem"] = summary["stdev"] / math.sqrt(len(data))
    return summary


def cohens_d(a: list[float], b: list[float]) -> float:
    """Cohen's d with a pooled standard deviation."""
    if len(a) < 2 or len(b) < 2:
        return 0.0
    va, vb = statistics.variance(a), statistics.variance(b)
    pooled = math.sqrt(((len(a) - 1) * va + (len(b) - 1) * vb) / (len(a) + len(b) - 2))
    if pooled == 0:
        return 0.0
    return (statistics.fmean(a) - statistics.fmean(b)) / pooled


def _t_sf(t: float, df: float) -> float:
    """Survival function of Student's t — scipy when present, else normal approx."""
    try:
        from scipy import stats as sps

        return float(sps.t.sf(t, df))
    except ImportError:
        # Cornish–Fisher-flavoured normal approximation; good to ~2 decimals
        # for df >= 5, which covers every realistic experiment analysis.
        z = t * (1 - 1 / (4 * df)) / math.sqrt(1 + t * t / (2 * df))
        return statistics.NormalDist().cdf(-z)


def welch_ttest(a: list[float], b: list[float]) -> dict[str, float]:
    """Welch's unequal-variance t-test → {t, df, p_value, cohens_d}."""
    if len(a) < 2 or len(b) < 2:
        return {"t": 0.0, "df": 0.0, "p_value": 1.0, "cohens_d": 0.0}
    va, vb = statistics.variance(a) / len(a), statistics.variance(b) / len(b)
    se = math.sqrt(va + vb)
    if se == 0:
        return {"t": 0.0, "df": float(len(a) + len(b) - 2), "p_value": 1.0, "cohens_d": 0.0}
    t = (statistics.fmean(a) - statistics.fmean(b)) / se
    df = (va + vb) ** 2 / (va**2 / (len(a) - 1) + vb**2 / (len(b) - 1))
    p = 2 * _t_sf(abs(t), df)
    return {"t": t, "df": df, "p_value": min(p, 1.0), "cohens_d": cohens_d(a, b)}


def required_sample_size(effect_size: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Per-group n for a two-sided two-sample test (normal approximation)."""
    if effect_size <= 0:
        return 0
    nd = statistics.NormalDist()
    z_alpha = nd.inv_cdf(1 - alpha / 2)
    z_power = nd.inv_cdf(power)
    return math.ceil(2 * ((z_alpha + z_power) / effect_size) ** 2)


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------


def register_tools(registry: ToolRegistry) -> None:
    from olivia.tools.registry import Tool

    registry.register(
        Tool(
            name="python_exec",
            description=(
                "Execute Python code in an isolated subprocess and return stdout/"
                "stderr. Use print() to emit results (JSON preferred)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "timeout": {"type": "number", "default": 30.0},
                },
                "required": ["code"],
            },
            fn=python_exec,
            risk=5,
        )
    )
    registry.register(
        Tool(
            name="symbolic_math",
            description=(
                "Symbolic mathematics via sympy: simplify, expand, factor, solve, diff, integrate."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "operation": {"type": "string", "enum": list(_OPERATIONS)},
                    "variable": {"type": "string", "default": "x"},
                },
                "required": ["expression"],
            },
            fn=symbolic_math,
            risk=1,
        )
    )
    registry.register(
        Tool(
            name="stats_test",
            description="Welch's t-test between two samples: t, df, p_value, cohens_d.",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "array", "items": {"type": "number"}},
                    "b": {"type": "array", "items": {"type": "number"}},
                },
                "required": ["a", "b"],
            },
            fn=welch_ttest,
            risk=1,
        )
    )
    registry.register(
        Tool(
            name="sample_size",
            description=(
                "Required per-group sample size for a target effect size, alpha, and power."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "effect_size": {"type": "number"},
                    "alpha": {"type": "number", "default": 0.05},
                    "power": {"type": "number", "default": 0.8},
                },
                "required": ["effect_size"],
            },
            fn=required_sample_size,
            risk=1,
        )
    )
