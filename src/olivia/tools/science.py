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
# Best-effort memory ceiling for the subprocess (Linux via resource.setrlimit).
# This is not an OS boundary: it contains accidental loops and allocations, not
# a determined adversary. Hostile workloads belong in a real container sandbox.
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
# Explicit denylist, in addition to the allowlist above: these never load even
# if _SAFE_IMPORTS is widened later.
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
            _traceback.print_exc(file=_sys.__stderr__)
            _sys.exit(1)
        """
    )


_SAFE_SYMPY_NAMES = frozenset(
    {
        "E",
        "I",
        "N",
        "Abs",
        "Add",
        "And",
        "Derivative",
        "EmptySet",
        "Eq",
        "Equivalent",
        "FiniteSet",
        "Float",
        "Function",
        "Ge",
        "Gt",
        "ImmutableMatrix",
        "Implies",
        "Integer",
        "Integral",
        "Intersection",
        "Interval",
        "Lambda",
        "Le",
        "Limit",
        "Lt",
        "Matrix",
        "MatrixSymbol",
        "Max",
        "Min",
        "Mul",
        "Ne",
        "Not",
        "Or",
        "Piecewise",
        "Pow",
        "Product",
        "Rational",
        "Sum",
        "Symbol",
        "Tuple",
        "Union",
        "Xor",
        "apart",
        "cancel",
        "ceiling",
        "conjugate",
        "det",
        "diag",
        "diff",
        "dsolve",
        "exp",
        "expand",
        "expand_trig",
        "eye",
        "factor",
        "factorint",
        "false",
        "floor",
        "frac",
        "gcd",
        "im",
        "integrate",
        "lcm",
        "limit",
        "linsolve",
        "ln",
        "log",
        "nan",
        "nonlinsolve",
        "nsimplify",
        "nsolve",
        "ones",
        "oo",
        "pi",
        "product",
        "re",
        "root",
        "series",
        "sign",
        "simplify",
        "solve",
        "solveset",
        "sqrt",
        "summation",
        "symbols",
        "together",
        "trace",
        "transpose",
        "trigsimp",
        "true",
        "var",
        "zeros",
        "zoo",
    }
)


def _safe_sympy_globals() -> dict[str, Any]:
    import sympy
    import sympy.functions

    globals_dict: dict[str, Any] = {
        "abs": abs,
        "min": min,
        "max": max,
        "__builtins__": {},
    }
    for name in _SAFE_SYMPY_NAMES:
        if hasattr(sympy, name):
            globals_dict[name] = getattr(sympy, name)
    for name, value in vars(sympy.functions).items():
        if not name.startswith("_") and callable(value):
            globals_dict.setdefault(name, value)
    globals_dict["e"] = sympy.E
    return globals_dict


_MAX_RESULT_DIGITS = 1000
_MAX_EXPONENT = 64
_MAX_COMBINATORIAL_ARGUMENT = 1000
_MAX_MATRIX_DIM = 64
_MAX_CONTAINER_ELEMENTS = 64
_MAX_DIFF_ORDER = 16
_MAX_SERIES_ORDER = 32
_MAX_SYSTEM_ITEMS = 16

_NUMERIC_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "E": math.e,
    "e": math.e,
    "I": 1.0,
}
_NUMBER_CONSTRUCTORS = frozenset({"Integer", "Float", "Rational"})
_SYMBOLIC_CONSTRUCTORS = frozenset({"Symbol", "Function", "symbols", "var"})
_CONTAINER_CONSTRUCTORS = frozenset(
    {"Tuple", "FiniteSet", "Interval", "Matrix", "ImmutableMatrix", "Piecewise"}
)
_COMBINATORIAL_CALLS = frozenset(
    {
        "factorial",
        "factorial2",
        "subfactorial",
        "gamma",
        "loggamma",
        "polygamma",
        "digamma",
        "trigamma",
        "beta",
        "uppergamma",
        "lowergamma",
        "fibonacci",
        "lucas",
        "tribonacci",
        "bell",
        "bernoulli",
        "catalan",
        "euler",
        "harmonic",
        "binomial",
        "ff",
        "rf",
        "fallingfactorial",
        "risingfactorial",
        "multinomial",
        "stirling",
        "partition",
        "factorint",
        "prime",
        "primerange",
        "totient",
        "divisors",
    }
)
_MATRIX_CONSTRUCTORS = frozenset(
    {"Matrix", "ImmutableMatrix", "MatrixSymbol", "eye", "zeros", "ones", "diag"}
)
_ITERATION_CALLS = frozenset({"summation", "product", "Sum", "Product"})
_DIFF_CALLS = frozenset({"diff", "Derivative"})
_INTEGRATE_CALLS = frozenset({"integrate", "Integral"})
_LIMIT_CALLS = frozenset({"limit", "Limit"})
_SYSTEM_SOLVER_CALLS = frozenset({"solve", "linsolve", "nonlinsolve"})
_SCALAR_EAGER_CALLS = frozenset(
    {
        "solveset",
        "dsolve",
        "nsolve",
        "expand",
        "expand_trig",
        "factor",
        "simplify",
        "trigsimp",
        "apart",
        "cancel",
        "together",
    }
)
_EAGER_SYMBOLIC_CALLS = (
    _ITERATION_CALLS
    | _DIFF_CALLS
    | _INTEGRATE_CALLS
    | _LIMIT_CALLS
    | _SYSTEM_SOLVER_CALLS
    | _SCALAR_EAGER_CALLS
    | frozenset({"series", "N"})
)
_ALLOWED_EXPR_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Name,
    ast.Constant,
    ast.Tuple,
    ast.List,
    ast.keyword,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.LShift,
    ast.RShift,
    ast.UAdd,
    ast.USub,
    ast.Load,
)


class ExpressionLimitError(ValueError):
    """Raised when an expression exceeds offline evaluation safety bounds."""


def _is_numeric_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) or (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _NUMBER_CONSTRUCTORS
    )


def _sequence_elements(node: ast.AST) -> list[ast.AST] | None:
    if isinstance(node, ast.Tuple | ast.List):
        return list(node.elts)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Tuple"
        and not node.keywords
    ):
        return list(node.args)
    return None


def _is_container_expr(node: ast.AST) -> bool:
    return _sequence_elements(node) is not None or (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _CONTAINER_CONSTRUCTORS
    )


def _is_symbol_node(node: ast.AST) -> bool:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Symbol"
        and not node.keywords
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return True
    return (
        isinstance(node, ast.Name)
        and node.id not in _NUMERIC_CONSTANTS
        and node.id not in _SAFE_SYMPY_NAMES
    )


def _require_no_keywords(node: ast.Call, name: str) -> None:
    if node.keywords:
        raise ExpressionLimitError(f"keyword arguments are not allowed for {name}()")


def _require_scalar_arg(
    arg: ast.AST,
    *,
    name: str,
    symbolic_degree_limit: int | None,
) -> float | None:
    if _is_container_expr(arg):
        raise ExpressionLimitError(f"structured container argument is not allowed for {name}()")
    return _ast_magnitude(arg, symbolic_degree_limit=symbolic_degree_limit)


def _require_bounded_numeric(
    arg: ast.AST,
    *,
    name: str,
    label: str,
    limit: int,
    symbolic_degree_limit: int | None,
) -> float:
    mag = _require_scalar_arg(arg, name=name, symbolic_degree_limit=symbolic_degree_limit)
    if mag is None or not math.isfinite(mag):
        raise ExpressionLimitError(
            f"{name}() {label} must have a bounded finite numeric value (<= {limit})"
        )
    if mag > limit:
        raise ExpressionLimitError(f"{name}() {label} {mag:g} exceeds limit of {limit}")
    return mag


def _check_power_bounds(
    left: float | None,
    right: float | None,
    *,
    symbolic_degree_limit: int | None,
) -> float | None:
    if right is None:
        return None
    if math.isinf(right):
        raise ExpressionLimitError("exponent exceeds offline evaluation limits")
    if left is None:
        if symbolic_degree_limit is not None and right > symbolic_degree_limit:
            raise ExpressionLimitError(
                f"a power of {right:g} exceeds the limit of {symbolic_degree_limit}"
            )
        return None
    if left in (0.0, 1.0):
        return left
    if math.isinf(left):
        raise ExpressionLimitError("base exceeds offline evaluation limits")
    scale = max(left, 1.0 / left)
    digits = right * math.log10(scale)
    if digits > _MAX_RESULT_DIGITS:
        raise ExpressionLimitError(
            f"a number of about 10^{digits:.3g} exceeds {_MAX_RESULT_DIGITS} digits"
        )
    return math.inf if digits > 300 else scale**right


def _ast_magnitude(node: ast.AST, *, symbolic_degree_limit: int | None) -> float | None:
    """Bound numeric growth and eager operations directly on the compiled AST."""
    if isinstance(node, ast.Expression):
        return _ast_magnitude(node.body, symbolic_degree_limit=symbolic_degree_limit)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float | str):
            return None
        try:
            val = abs(float(node.value))
        except ValueError:
            return None
        if val > 0 and math.log10(val) > _MAX_RESULT_DIGITS:
            raise ExpressionLimitError(f"literal exceeds {_MAX_RESULT_DIGITS} digits")
        return val
    if isinstance(node, ast.Name):
        return _NUMERIC_CONSTANTS.get(node.id)
    if isinstance(node, ast.UnaryOp):
        if _is_container_expr(node.operand):
            raise ExpressionLimitError("container operands are not allowed in unary operations")
        return _ast_magnitude(node.operand, symbolic_degree_limit=symbolic_degree_limit)
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.LShift | ast.RShift):
            raise ExpressionLimitError(
                "bit-shift operators are not allowed in symbolic expressions"
            )
        if _is_container_expr(node.left) or _is_container_expr(node.right):
            raise ExpressionLimitError(
                "container operands are not allowed in arithmetic expressions"
            )
        if (isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)) or (
            isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)
        ):
            raise ExpressionLimitError("string operands are not allowed in arithmetic expressions")
        left = _ast_magnitude(node.left, symbolic_degree_limit=symbolic_degree_limit)
        right = _ast_magnitude(node.right, symbolic_degree_limit=symbolic_degree_limit)
        if isinstance(node.op, ast.Pow):
            return _check_power_bounds(left, right, symbolic_degree_limit=symbolic_degree_limit)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add | ast.Sub):
            out = left + right
        elif isinstance(node.op, ast.Mult):
            out = left * right
        elif isinstance(node.op, ast.Div) and _is_numeric_literal(node.right) and right >= 1:
            out = left / right
        else:
            return math.inf
        if math.isfinite(out) and out > 0 and math.log10(out) > _MAX_RESULT_DIGITS:
            raise ExpressionLimitError(f"numeric result exceeds {_MAX_RESULT_DIGITS} digits")
        return out
    if isinstance(node, ast.Call):
        return _call_ast_magnitude(node, symbolic_degree_limit=symbolic_degree_limit)
    if isinstance(node, ast.Tuple | ast.List):
        if len(node.elts) > _MAX_CONTAINER_ELEMENTS:
            raise ExpressionLimitError(
                f"container length {len(node.elts)} exceeds limit of {_MAX_CONTAINER_ELEMENTS}"
            )
        for el in node.elts:
            _ast_magnitude(el, symbolic_degree_limit=symbolic_degree_limit)
        return None
    raise ExpressionLimitError(f"unsupported expression construct: {type(node).__name__}")


def _validate_iteration_call(node: ast.Call, name: str, *, child_limit: int | None) -> None:
    _require_no_keywords(node, name)
    if len(node.args) < 2:
        raise ExpressionLimitError(f"{name}() requires an expression and bounded limit tuple")
    _require_scalar_arg(node.args[0], name=name, symbolic_degree_limit=child_limit)
    total_steps = 1.0
    for spec in node.args[1:]:
        elts = _sequence_elements(spec)
        if elts is None or len(elts) != 3 or not _is_symbol_node(elts[0]):
            raise ExpressionLimitError(
                f"{name}() limit specification must be a 3-tuple (symbol, lower, upper)"
            )
        lower = _require_bounded_numeric(
            elts[1],
            name=name,
            label="lower bound",
            limit=_MAX_COMBINATORIAL_ARGUMENT,
            symbolic_degree_limit=child_limit,
        )
        upper = _require_bounded_numeric(
            elts[2],
            name=name,
            label="upper bound",
            limit=_MAX_COMBINATORIAL_ARGUMENT,
            symbolic_degree_limit=child_limit,
        )
        span = lower + upper + 1.0
        total_steps *= span
        if span > _MAX_COMBINATORIAL_ARGUMENT + 1 or total_steps > _MAX_COMBINATORIAL_ARGUMENT:
            raise ExpressionLimitError(
                f"{name}() iteration span exceeds limit of {_MAX_COMBINATORIAL_ARGUMENT}"
            )


def _validate_diff_call(node: ast.Call, name: str, *, child_limit: int | None) -> None:
    _require_no_keywords(node, name)
    if not node.args:
        raise ExpressionLimitError(f"{name}() requires at least one argument")
    _require_scalar_arg(node.args[0], name=name, symbolic_degree_limit=child_limit)
    total_order = 0.0
    for spec in node.args[1:]:
        elts = _sequence_elements(spec)
        if elts is not None:
            if len(elts) != 2 or not _is_symbol_node(elts[0]):
                raise ExpressionLimitError(
                    f"{name}() tuple argument must have shape (symbol, order)"
                )
            total_order += _require_bounded_numeric(
                elts[1],
                name=name,
                label="order",
                limit=_MAX_DIFF_ORDER,
                symbolic_degree_limit=child_limit,
            )
        elif _is_symbol_node(spec):
            total_order += 1.0
        else:
            total_order += _require_bounded_numeric(
                spec,
                name=name,
                label="order",
                limit=_MAX_DIFF_ORDER,
                symbolic_degree_limit=child_limit,
            )
        if total_order > _MAX_DIFF_ORDER:
            raise ExpressionLimitError(
                f"{name}() cumulative order {total_order:g} exceeds limit of {_MAX_DIFF_ORDER}"
            )


def _validate_integrate_call(node: ast.Call, name: str, *, child_limit: int | None) -> None:
    _require_no_keywords(node, name)
    if not node.args:
        raise ExpressionLimitError(f"{name}() requires at least one argument")
    _require_scalar_arg(node.args[0], name=name, symbolic_degree_limit=child_limit)
    for spec in node.args[1:]:
        elts = _sequence_elements(spec)
        if elts is not None:
            if len(elts) != 3 or not _is_symbol_node(elts[0]):
                raise ExpressionLimitError(
                    f"{name}() limit specification must be a 3-tuple (symbol, lower, upper)"
                )
            for bound_node in elts[1:]:
                mag = _require_scalar_arg(bound_node, name=name, symbolic_degree_limit=child_limit)
                if mag is not None and mag > _MAX_COMBINATORIAL_ARGUMENT:
                    raise ExpressionLimitError(
                        f"{name}() bound {mag:g} exceeds limit of {_MAX_COMBINATORIAL_ARGUMENT}"
                    )
        elif not _is_symbol_node(spec):
            raise ExpressionLimitError(
                f"{name}() integration variable must be a symbol or (symbol, lower, upper) tuple"
            )


def _validate_series_call(node: ast.Call, *, child_limit: int | None) -> None:
    if not 1 <= len(node.args) <= 5:
        raise ExpressionLimitError("series() expects 1 to 5 positional arguments")
    allowed_kw = {"x", "x0", "n", "dir"}
    for idx, arg in enumerate(node.args):
        if idx == 3:
            _require_bounded_numeric(
                arg,
                name="series",
                label="order n",
                limit=_MAX_SERIES_ORDER,
                symbolic_degree_limit=child_limit,
            )
        else:
            mag = _require_scalar_arg(arg, name="series", symbolic_degree_limit=child_limit)
            if mag is not None and mag > _MAX_COMBINATORIAL_ARGUMENT:
                raise ExpressionLimitError(
                    f"series() argument {mag:g} exceeds limit of {_MAX_COMBINATORIAL_ARGUMENT}"
                )
    for kw in node.keywords:
        if kw.arg not in allowed_kw:
            raise ExpressionLimitError(f"unsupported keyword '{kw.arg}' for series()")
        if kw.arg == "n":
            _require_bounded_numeric(
                kw.value,
                name="series",
                label="order n",
                limit=_MAX_SERIES_ORDER,
                symbolic_degree_limit=child_limit,
            )
        elif kw.arg == "dir":
            if not isinstance(kw.value, ast.Constant) or kw.value.value not in ("+", "-", "+-"):
                raise ExpressionLimitError("series() dir must be '+', '-', or '+-'")
        else:
            mag = _require_scalar_arg(kw.value, name="series", symbolic_degree_limit=child_limit)
            if mag is not None and mag > _MAX_COMBINATORIAL_ARGUMENT:
                raise ExpressionLimitError(
                    f"series() {kw.arg} exceeds limit of {_MAX_COMBINATORIAL_ARGUMENT}"
                )


def _validate_limit_call(node: ast.Call, name: str, *, child_limit: int | None) -> None:
    if not 3 <= len(node.args) <= 4:
        raise ExpressionLimitError(f"{name}() expects 3 or 4 positional arguments")
    for idx, arg in enumerate(node.args):
        if idx == 3:
            if not isinstance(arg, ast.Constant) or arg.value not in ("+", "-", "+-"):
                raise ExpressionLimitError(f"{name}() direction must be '+', '-', or '+-'")
        else:
            mag = _require_scalar_arg(arg, name=name, symbolic_degree_limit=child_limit)
            if mag is not None and mag > _MAX_COMBINATORIAL_ARGUMENT:
                raise ExpressionLimitError(
                    f"{name}() argument {mag:g} exceeds limit of {_MAX_COMBINATORIAL_ARGUMENT}"
                )
    for kw in node.keywords:
        if (
            kw.arg != "dir"
            or not isinstance(kw.value, ast.Constant)
            or kw.value.value
            not in (
                "+",
                "-",
                "+-",
            )
        ):
            raise ExpressionLimitError(f"unsupported keyword '{kw.arg}' for {name}()")


def _validate_matrix_call(node: ast.Call, name: str, *, symbolic_degree_limit: int | None) -> None:
    _require_no_keywords(node, name)
    if name in ("eye", "zeros", "ones"):
        if not 1 <= len(node.args) <= 2:
            raise ExpressionLimitError(f"{name}() expects 1 or 2 dimension arguments")
        for arg in node.args:
            _require_bounded_numeric(
                arg,
                name=name,
                label="dimension",
                limit=_MAX_MATRIX_DIM,
                symbolic_degree_limit=symbolic_degree_limit,
            )
        return
    if name == "MatrixSymbol":
        if (
            len(node.args) != 3
            or not isinstance(node.args[0], ast.Constant)
            or not isinstance(node.args[0].value, str)
        ):
            raise ExpressionLimitError("MatrixSymbol() expects (name, rows, cols)")
        for arg in node.args[1:]:
            _require_bounded_numeric(
                arg,
                name=name,
                label="dimension",
                limit=_MAX_MATRIX_DIM,
                symbolic_degree_limit=symbolic_degree_limit,
            )
        return
    if name in ("Matrix", "ImmutableMatrix"):
        if len(node.args) == 1:
            rows = _sequence_elements(node.args[0])
            if rows is None or len(rows) > _MAX_MATRIX_DIM:
                raise ExpressionLimitError(
                    f"{name}() expects a sequence with at most {_MAX_MATRIX_DIM} rows"
                )
            for row in rows:
                cols = _sequence_elements(row)
                if cols is not None:
                    if len(cols) > _MAX_MATRIX_DIM:
                        raise ExpressionLimitError(
                            f"{name}() row exceeds limit of {_MAX_MATRIX_DIM} columns"
                        )
                    for cell in cols:
                        _require_scalar_arg(
                            cell, name=name, symbolic_degree_limit=symbolic_degree_limit
                        )
                else:
                    _require_scalar_arg(row, name=name, symbolic_degree_limit=symbolic_degree_limit)
            return
        if len(node.args) == 3:
            r = _require_bounded_numeric(
                node.args[0],
                name=name,
                label="rows",
                limit=_MAX_MATRIX_DIM,
                symbolic_degree_limit=symbolic_degree_limit,
            )
            c = _require_bounded_numeric(
                node.args[1],
                name=name,
                label="cols",
                limit=_MAX_MATRIX_DIM,
                symbolic_degree_limit=symbolic_degree_limit,
            )
            flat = _sequence_elements(node.args[2])
            if (
                flat is None
                or len(flat) > _MAX_MATRIX_DIM * _MAX_MATRIX_DIM
                or r * c > (_MAX_MATRIX_DIM * _MAX_MATRIX_DIM)
            ):
                raise ExpressionLimitError(f"{name}() flat entries exceed matrix bounds")
            for cell in flat:
                _require_scalar_arg(cell, name=name, symbolic_degree_limit=symbolic_degree_limit)
            return
        raise ExpressionLimitError(f"unsupported argument shape for {name}()")
    # diag(*args)
    if not 1 <= len(node.args) <= _MAX_MATRIX_DIM:
        raise ExpressionLimitError(f"diag() expects 1 to {_MAX_MATRIX_DIM} arguments")
    for arg in node.args:
        if (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Name)
            and arg.func.id in _MATRIX_CONSTRUCTORS
        ):
            _ast_magnitude(arg, symbolic_degree_limit=symbolic_degree_limit)
        else:
            _require_scalar_arg(arg, name="diag", symbolic_degree_limit=symbolic_degree_limit)


def _call_ast_magnitude(node: ast.Call, *, symbolic_degree_limit: int | None) -> float | None:
    name = node.func.id if isinstance(node.func, ast.Name) else ""
    if len(node.args) + len(node.keywords) > _MAX_CONTAINER_ELEMENTS:
        raise ExpressionLimitError(
            f"{name}() with {len(node.args) + len(node.keywords)} arguments exceeds limit"
        )
    child_limit = (
        _MAX_EXPONENT
        if name in _EAGER_SYMBOLIC_CALLS and symbolic_degree_limit is None
        else symbolic_degree_limit
    )

    if name == "Pow":
        _require_no_keywords(node, name)
        if len(node.args) != 2:
            raise ExpressionLimitError("Pow() requires exactly 2 scalar arguments")
        left = _require_scalar_arg(node.args[0], name=name, symbolic_degree_limit=child_limit)
        right = _require_scalar_arg(node.args[1], name=name, symbolic_degree_limit=child_limit)
        return _check_power_bounds(left, right, symbolic_degree_limit=symbolic_degree_limit)

    if name in _SYMBOLIC_CONSTRUCTORS:
        for arg in node.args:
            _require_scalar_arg(arg, name=name, symbolic_degree_limit=child_limit)
        for kw in node.keywords:
            _require_scalar_arg(kw.value, name=name, symbolic_degree_limit=child_limit)
        return None

    if name in _NUMBER_CONSTRUCTORS:
        _require_no_keywords(node, name)
        nums = [
            _require_scalar_arg(arg, name=name, symbolic_degree_limit=child_limit)
            for arg in node.args
        ]
        if name == "Rational" and len(nums) == 2 and None not in nums:
            return nums[0]
        return nums[0] if nums else None

    if name in _MATRIX_CONSTRUCTORS:
        _validate_matrix_call(node, name, symbolic_degree_limit=child_limit)
        return None

    if name in _ITERATION_CALLS:
        _validate_iteration_call(node, name, child_limit=child_limit)
        return None

    if name in _DIFF_CALLS:
        _validate_diff_call(node, name, child_limit=child_limit)
        return None

    if name in _INTEGRATE_CALLS:
        _validate_integrate_call(node, name, child_limit=child_limit)
        return None

    if name == "series":
        _validate_series_call(node, child_limit=child_limit)
        return None

    if name in _LIMIT_CALLS:
        _validate_limit_call(node, name, child_limit=child_limit)
        return None

    if name == "N":
        _require_no_keywords(node, name)
        if not 1 <= len(node.args) <= 2:
            raise ExpressionLimitError("N() expects 1 or 2 scalar arguments")
        val = _require_scalar_arg(node.args[0], name=name, symbolic_degree_limit=child_limit)
        if len(node.args) == 2:
            _require_bounded_numeric(
                node.args[1],
                name="N",
                label="precision",
                limit=_MAX_RESULT_DIGITS,
                symbolic_degree_limit=child_limit,
            )
        return val

    if name in _SYSTEM_SOLVER_CALLS:
        _require_no_keywords(node, name)
        if not 1 <= len(node.args) <= 3:
            raise ExpressionLimitError(f"{name}() expects 1 to 3 arguments")
        for arg in node.args:
            elts = _sequence_elements(arg)
            if elts is not None:
                if len(elts) > _MAX_SYSTEM_ITEMS:
                    raise ExpressionLimitError(
                        f"{name}() sequence exceeds limit of {_MAX_SYSTEM_ITEMS} items"
                    )
                for el in elts:
                    mag = _require_scalar_arg(el, name=name, symbolic_degree_limit=child_limit)
                    if mag is not None and mag > _MAX_COMBINATORIAL_ARGUMENT:
                        raise ExpressionLimitError(
                            f"{name}() arg {mag:g} exceeds limit of {_MAX_COMBINATORIAL_ARGUMENT}"
                        )
            else:
                mag = _require_scalar_arg(arg, name=name, symbolic_degree_limit=child_limit)
                if mag is not None and mag > _MAX_COMBINATORIAL_ARGUMENT:
                    raise ExpressionLimitError(
                        f"{name}() argument {mag:g} exceeds limit of {_MAX_COMBINATORIAL_ARGUMENT}"
                    )
        return None

    if name in _SCALAR_EAGER_CALLS:
        _require_no_keywords(node, name)
        for arg in node.args:
            mag = _require_scalar_arg(arg, name=name, symbolic_degree_limit=child_limit)
            if mag is not None and mag > _MAX_COMBINATORIAL_ARGUMENT:
                raise ExpressionLimitError(
                    f"{name}() argument {mag:g} exceeds limit of {_MAX_COMBINATORIAL_ARGUMENT}"
                )
        return None

    if name in _CONTAINER_CONSTRUCTORS:
        _require_no_keywords(node, name)
        for arg in node.args:
            _ast_magnitude(arg, symbolic_degree_limit=child_limit)
        return None

    _require_no_keywords(node, name)
    args = [
        _require_scalar_arg(arg, name=name, symbolic_degree_limit=child_limit) for arg in node.args
    ]
    known = [arg for arg in args if arg is not None]
    if name.lower() in _COMBINATORIAL_CALLS:
        for mag_val in known:
            if not math.isfinite(mag_val) or mag_val > _MAX_COMBINATORIAL_ARGUMENT:
                raise ExpressionLimitError(
                    f"{name}({mag_val:g}) exceeds the limit of {_MAX_COMBINATORIAL_ARGUMENT}"
                )
        if not known or len(known) != len(args):
            return None
        largest = max(known)
        return math.exp(min(math.lgamma(largest + 1), 700.0))
    if not known or len(known) != len(args):
        return None
    return max(known)


def _check_expression(code: str, globals_dict: dict[str, Any]) -> ast.Expression:
    tree = ast.parse(code, mode="eval")
    allowed_names = set(globals_dict) - {"__builtins__"}
    allowed_calls = {name for name in allowed_names if callable(globals_dict[name])}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            raise ValueError("attributes are not allowed in symbolic expressions")
        if not isinstance(node, _ALLOWED_EXPR_NODES):
            raise ValueError(
                f"unsupported construct '{type(node).__name__}' in symbolic expression"
            )
        if isinstance(node, ast.Call) and (
            not isinstance(node.func, ast.Name) or node.func.id not in allowed_calls
        ):
            raise ValueError("only known mathematical functions may be called")
        if isinstance(node, ast.Name) and node.id not in allowed_names:
            raise ValueError(f"unknown name '{node.id}' in symbolic expression")
    return tree


def safe_sympify(
    expression: str,
    implicit_multiplication: bool = False,
    *,
    bound_symbolic_degree: bool = False,
    max_symbolic_degree: int | None = None,
):
    """Parse a mathematical expression without Python builtins or imports.

    Validates numeric growth, combinatorial arguments, and eager symbolic
    operations directly on the compiled AST before evaluation.
    """
    from tokenize import TokenError

    from sympy.parsing.sympy_parser import (
        implicit_multiplication_application,
        standard_transformations,
        stringify_expr,
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
    globals_dict = _safe_sympy_globals()
    try:
        code = stringify_expr(expression.replace("^", "**"), {}, globals_dict, transformations)
        tree = _check_expression(code, globals_dict)
    except (SyntaxError, TokenError) as exc:
        raise ValueError("invalid mathematical expression") from exc
    symbolic_limit = (
        max_symbolic_degree
        if max_symbolic_degree is not None
        else (_MAX_EXPONENT if bound_symbolic_degree else None)
    )
    _ast_magnitude(tree, symbolic_degree_limit=symbolic_limit)
    return eval(compile(tree, "<olivia-expression>", "eval"), globals_dict)  # nosec B307 - expression is validated by _check_expression, _CodePolicy, and _ast_magnitude


def python_exec(code: str, timeout: float = 30.0) -> dict[str, Any]:
    """Run restricted pure-Python code; return ``{ok, stdout, stderr}``.

    This is a constrained simulation runner, not a complete OS security
    boundary. Hostile workloads still belong in a real container or job
    sandbox. Filesystem/process/network imports and credential-bearing
    environment variables are intentionally unavailable here. On Linux the
    subprocess also gets best-effort memory (RLIMIT_AS) and CPU limits; on
    Windows only the timeout and the allowlist apply.
    """
    try:
        _validate_code(code)
        timeout = min(max(float(timeout), 0.1), _MAX_TIMEOUT)

        def _preexec_limit() -> None:
            # Linux/POSIX only: best-effort containment, not an OS boundary.
            try:
                import resource as _res

                setrlimit = getattr(_res, "setrlimit", None)
                rlimit_as = getattr(_res, "RLIMIT_AS", None)
                rlimit_cpu = getattr(_res, "RLIMIT_CPU", None)
                if callable(setrlimit) and rlimit_as is not None and rlimit_cpu is not None:
                    setrlimit(rlimit_as, (_MAX_MEMORY_BYTES, _MAX_MEMORY_BYTES))
                    cpu = max(int(timeout) + 5, 35)
                    setrlimit(rlimit_cpu, (cpu, cpu))
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
        expr = safe_sympify(
            expression,
            implicit_multiplication=True,
            bound_symbolic_degree=(operation == "solve"),
            max_symbolic_degree=(256 if operation in ("expand", "factor") else None),
        )
        symbol = sympy.Symbol(variable)
        if symbol not in expr.free_symbols and expr.free_symbols:
            symbol = sorted(expr.free_symbols, key=lambda s: s.name)[0]
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
    if not math.isfinite(effect_size) or effect_size <= 0:
        return 0
    if not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError("alpha and power must be between 0 and 1")
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
