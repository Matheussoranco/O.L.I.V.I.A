"""Scientific computation tools — sandboxed Python, symbolic math, statistics.

Statistics run on the standard library (``statistics.NormalDist``); scipy and
sympy upgrade precision when installed but are never required.  ``python_exec``
runs code in an isolated subprocess (``-I``) with a hard timeout — it is the
execution backend for experiment simulations designed by the research cycle.
"""

from __future__ import annotations

import ast
import logging
import math
import os
import re
import statistics
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from olivia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Restricted execution
# ---------------------------------------------------------------------------


_MAX_CODE_CHARS = 50_000
_MAX_OUTPUT_CHARS = 20_000
_MAX_TIMEOUT = 30.0
# Limite de memória do subprocesso (Linux via resource.setrlimit). Não é
# boundary OS: `python_exec` é um sandbox incompleto — contenção best-effort
# contra loops/alocações acidentais, NÃO contra adversário determinado.
# Carga hostil pertence a container/job sandbox real (Docker/gVisor).
_MAX_MEMORY_BYTES = int(os.environ.get("OLIVIA_PYEXEC_MAX_BYTES", str(256 * 1024 * 1024)))
_SAFE_IMPORTS = {
    "collections",
    "decimal",
    "fractions",
    "itertools",
    "json",
    "math",
    "random",
    "statistics",
}
# Bloqueio explícito (defesa em profundidade além do allowlist acima): estes
# nunca passam, mesmo que alguém amplie _SAFE_IMPORTS no futuro.
_BLOCKED_MODULES = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "pathlib",
    "shutil",
    "tempfile",
    "ctypes",
    "importlib",
    "inspect",
    "ast",
    "builtins",
    "__builtin__",
    "io",
    "multiprocessing",
    "threading",
    "signal",
    "pty",
    "fcntl",
    "urllib",
    "http",
    "ssl",
    "pickle",
    "marshal",
    "code",
    "codecs",
}
_BLOCKED_CALLS = {
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}


class _UnsafeCode(ValueError):
    """A code snippet violates the restricted execution policy."""


class _CodePolicy(ast.NodeVisitor):
    """Reject filesystem, process, reflection, and dynamic-code primitives."""

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".", 1)[0]
            if top in _BLOCKED_MODULES:
                raise _UnsafeCode(f"import '{alias.name}' is blocked (not an OS boundary)")
            if top not in _SAFE_IMPORTS:
                raise _UnsafeCode(f"import '{alias.name}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        top = (node.module or "").split(".", 1)[0]
        if top in _BLOCKED_MODULES or not node.module:
            raise _UnsafeCode(f"import '{node.module or ''}' is blocked (not an OS boundary)")
        if top not in _SAFE_IMPORTS:
            raise _UnsafeCode(f"import '{node.module or ''}' is not allowed")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("_") or node.id in _BLOCKED_CALLS:
            raise _UnsafeCode(f"name '{node.id}' is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            raise _UnsafeCode(f"private attribute '{node.attr}' is not allowed")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and "__" in node.value:
            raise _UnsafeCode("dunder strings are not allowed")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_CALLS:
            raise _UnsafeCode(f"call '{node.func.id}' is not allowed")
        self.generic_visit(node)


def _validate_code(code: str) -> None:
    if not isinstance(code, str) or not code.strip():
        raise _UnsafeCode("code must be a non-empty string")
    if len(code) > _MAX_CODE_CHARS:
        raise _UnsafeCode(f"code exceeds {_MAX_CODE_CHARS} characters")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise _UnsafeCode(f"invalid Python: {exc}") from exc
    _CodePolicy().visit(tree)


def _safe_environment() -> dict[str, str]:
    """Keep interpreter plumbing but do not expose user credentials."""
    keep = {"LANG", "LC_ALL", "PATH", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "WINDIR"}
    return {key: value for key, value in os.environ.items() if key in keep}


def _restricted_wrapper(code: str) -> str:
    """Build a subprocess wrapper with a small builtin and import surface."""
    return textwrap.dedent(
        f"""
        import builtins as _builtins
        import io as _io
        import sys as _sys
        import traceback as _traceback

        class _LimitedWriter(_io.TextIOBase):
            def __init__(self, stream, limit):
                self.stream = stream
                self.limit = limit
                self.count = 0

            def write(self, value):
                value = str(value)
                remaining = self.limit - self.count
                if remaining <= 0:
                    raise RuntimeError("output limit exceeded")
                self.stream.write(value[:remaining])
                self.stream.flush()
                self.count += min(len(value), remaining)
                if len(value) > remaining:
                    raise RuntimeError("output limit exceeded")
                return len(value)

            def flush(self):
                self.stream.flush()

        _safe_modules = {sorted(_SAFE_IMPORTS)!r}
        _real_import = _builtins.__import__
        def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            if level or name.split('.', 1)[0] not in _safe_modules:
                raise ImportError("module is not allowed by the OLIVIA execution policy")
            return _real_import(name, globals, locals, fromlist, level)

        _safe_builtins = {{
            name: getattr(_builtins, name) for name in (
                "ArithmeticError", "AssertionError", "BaseException", "Exception",
                "TypeError", "ValueError", "RuntimeError",
                "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
                "int", "isinstance", "len", "list", "map", "max", "min", "print",
                "range", "repr", "round", "set", "sorted", "str", "sum", "tuple",
                "zip",
            )
        }}
        _safe_builtins.update({{"False": False, "None": None, "True": True}})
        _safe_builtins["__import__"] = _safe_import
        _globals = {{"__name__": "__main__", "__builtins__": _safe_builtins}}
        _sys.stdout = _LimitedWriter(_sys.__stdout__, {_MAX_OUTPUT_CHARS})
        _sys.stderr = _LimitedWriter(_sys.__stderr__, 4000)
        try:
            exec(compile({code!r}, "<olivia-restricted>", "exec"), _globals, _globals)
        except BaseException:
            _traceback.print_exc(file=_sys.__stderr__.stream)
            _sys.exit(1)
        """
    )


def safe_sympify(expression: str, implicit_multiplication: bool = False):
    """Parse a mathematical expression without Python builtins or imports."""
    import sympy
    from sympy.parsing.sympy_parser import (
        implicit_multiplication_application,
        parse_expr,
        standard_transformations,
    )

    if not isinstance(expression, str) or not expression.strip() or len(expression) > 10_000:
        raise ValueError("expression is empty or too long")
    if "__" in expression or any(
        token.startswith("_") for token in re.findall(r"[A-Za-z_]\w*", expression)
    ):
        raise ValueError("private names are not allowed")
    try:
        _CodePolicy().visit(ast.parse(expression, mode="eval"))
    except SyntaxError:
        if not implicit_multiplication or not re.fullmatch(
            r"[A-Za-z0-9_+\-*/^().,\s]+", expression
        ):
            raise ValueError("invalid mathematical expression") from None
    transformations = standard_transformations
    if implicit_multiplication:
        transformations = (*transformations, implicit_multiplication_application)
    globals_dict = {name: value for name, value in vars(sympy).items() if not name.startswith("_")}
    globals_dict["e"] = sympy.E
    globals_dict["__builtins__"] = {}
    return parse_expr(
        expression.replace("^", "**"),
        transformations=transformations,
        global_dict=globals_dict,
    )


def python_exec(code: str, timeout: float = 30.0) -> dict[str, Any]:
    """Run restricted pure-Python code; return ``{ok, stdout, stderr}``.

    This is a constrained simulation runner, not a complete OS security
    boundary (PT: NÃO é boundary OS — não use contra código hostil).
    Hostile workloads still belong in a real container or job
    sandbox. Filesystem/process/network imports and credential-bearing
    environment variables are intentionally unavailable here. No Linux,
    aplica-se ainda limite de memória (RLIMIT_AS) + CPU best-effort além
    do timeout; no Windows vale só timeout + allowlist.
    """
    try:
        _validate_code(code)
        timeout = min(max(float(timeout), 0.1), _MAX_TIMEOUT)

        def _preexec_limit() -> None:
            # Só Linux/POSIX: contenção best-effort, não boundary OS.
            try:
                import resource as _res

                _res.setrlimit(_res.RLIMIT_AS, (_MAX_MEMORY_BYTES, _MAX_MEMORY_BYTES))
                cpu = max(int(timeout) + 5, 35)
                _res.setrlimit(_res.RLIMIT_CPU, (cpu, cpu))
            except Exception:
                pass

        proc = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", "-c", _restricted_wrapper(code)],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=_safe_environment(),
            preexec_fn=_preexec_limit if os.name != "nt" else None,
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout[-_MAX_OUTPUT_CHARS:],
            "stderr": proc.stderr[-4000:],
        }
    except _UnsafeCode as exc:
        return {"ok": False, "stdout": "", "stderr": f"execution blocked: {exc}"}
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
        if not isinstance(variable, str) or not variable.isidentifier() or variable.startswith("_"):
            return "error: invalid variable name"
        symbol = sympy.Symbol(variable)
        expr = safe_sympify(expression)
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
                    "timeout": {
                        "type": "number",
                        "default": 30.0,
                        "minimum": 0.1,
                        "maximum": 30.0,
                    },
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
