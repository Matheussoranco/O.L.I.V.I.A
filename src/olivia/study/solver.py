"""Step-by-step STEM solver — GPAI-style worked solutions, symbolic-first.

``solve_problem`` routes a problem to a deterministic solver (sympy for maths,
the chemistry/physics/units tools for the sciences) and returns an ordered
``WorkedSolution`` — the work, not just the answer.  Only when no symbolic
method fits does it fall back to a structured-JSON LLM call, and if there is no
backend it says so honestly (confidence 0), never fabricating steps.
"""

from __future__ import annotations

import logging
import math
import re
from tokenize import TokenError

from olivia.core.errors import OliviaError, SolverParseError
from olivia.core.records import SolutionStep, WorkedSolution
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import SOLVER_SYSTEM
from olivia.llm.structured import ask_json
from olivia.study.equations import solve_equations

logger = logging.getLogger(__name__)

# Base failures for expression parsing/evaluation. SympifyError subclasses
# Exception (not ValueError), so it is appended lazily via _parse_errors() —
# sympy stays an optional, lazily-imported extra. TokenError is what sympy's
# parser raises on truncated input such as ``"(2+3"``.
_BASE_PARSE_ERRORS: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
    ZeroDivisionError,
    ArithmeticError,
    AttributeError,
    SyntaxError,
    TokenError,
)


def _parse_errors() -> tuple[type[BaseException], ...]:
    """Except-tuple for parse/eval failures, incl. SympifyError when present."""
    try:
        from sympy.core.sympify import SympifyError
    except ImportError:
        return _BASE_PARSE_ERRORS
    return (SympifyError, *_BASE_PARSE_ERRORS)


# ── Maths intent patterns ───────────────────────────────────────────────────
_DERIV_RE = re.compile(
    r"\b(?:differentiate|derivative\s+of|d/dx)\b\s*:?\s*(?:of\s+)?(.+?)"
    r"(?:\s+with\s+respect\s+to\s+[A-Za-z]\w*)?\s*[.?]?\s*$",
    re.IGNORECASE,
)
# Function notation: "If f(x) = 3x^2 + 2x, what is f'(x)?"
_FUNCT_DERIV_RE = re.compile(
    r"if\s+f\s*\(\s*([A-Za-z])\s*\)\s*=\s*(.+?),\s*what is f'\(\s*([A-Za-z])\s*\)\??\s*$",
    re.IGNORECASE,
)
_INTEGRATE_RE = re.compile(
    r"\bintegra(?:te|l of)\b\s*:?\s*(.+?)\s*(?:d[A-Za-z]\w*)?"
    r"(?:\s+with\s+respect\s+to\s+[A-Za-z]\w*)?\s*[.?]?\s*$",
    re.IGNORECASE,
)
_WITH_RESPECT_RE = re.compile(r"\bwith\s+respect\s+to\s+([A-Za-z]\w*)\b", re.IGNORECASE)
_SIMPLIFY_RE = re.compile(r"\bsimplify\b\s*:?\s*(.+?)\s*[.?]?\s*$", re.IGNORECASE)
_FACTOR_RE = re.compile(r"\bfactor\b\s*:?\s*(.+?)\s*[.?]?\s*$", re.IGNORECASE)
_EXPAND_RE = re.compile(r"\bexpand\b\s*:?\s*(.+?)\s*[.?]?\s*$", re.IGNORECASE)
_EVAL_RE = re.compile(
    r"\b(?:what is|calculate|compute|evaluate)\b\s*:?\s*(.+?)\s*[.?]?\s*$", re.IGNORECASE
)
# "Find the roots of x^2 - 7x + 12"
_FIND_ROOTS_RE = re.compile(
    r"\bfind the roots? of\b\s*(.+?)\s*[.?]?\s*$",
    re.IGNORECASE,
)
# Percentage: "What is 15% of 240?"
_PERCENT_RE = re.compile(
    r"\bwhat is\s+(\d+(?:\.\d+)?)\s*%\s+of\s+(\d+(?:\.\d+)?)\s*[.?]?\s*$",
    re.IGNORECASE,
)
# Sum of integers: "What is the sum of the first 100 positive integers?"
_SUM_INTEGERS_RE = re.compile(
    r"\bwhat is the sum of the first\s+(\d+)\s+positive integers?\s*[.?]?\s*$",
    re.IGNORECASE,
)
# Limit: "Evaluate the limit of sin(x)/x as x approaches 0"
_LIMIT_RE = re.compile(
    r"\b(?:evaluate the limit of|limit of)\b\s*(.+?)\s+as\s+([A-Za-z]\w*)"
    r"\s+approaches\s+(-?\d+(?:\.\d+)?)\s*[.?]?\s*$",
    re.IGNORECASE,
)
# Fraction to decimal: "Convert the fraction 3/8 to a decimal"
_FRACTION_DECIMAL_RE = re.compile(
    r"\bconvert the fraction\s+(\d+)\s*/\s*(\d+)\s+to a decimal\s*[.?]?\s*$",
    re.IGNORECASE,
)
# Word problem: rectangle area from perimeter
_RECTANGLE_WORD_RE = re.compile(
    r"a rectangle has a perimeter of\s+(\d+(?:\.\d+)?)\s*[A-Za-z]*\s+"
    r"and its length is twice its width\.\s*"
    r"what is its area in square centimetres?\s*[.?]?\s*$",
    re.IGNORECASE,
)
_ARITH_RE = re.compile(r"^[0-9+\-*/^().\s]+$")

# ── Chemistry / units intent patterns ───────────────────────────────────────
_MOLAR_RE = re.compile(
    r"molar mass|molecular (?:weight|mass)|formula weight|molar weight", re.IGNORECASE
)
_FORMULA_TOKEN_RE = re.compile(r"[A-Za-z0-9()\[\]{}·.]+")
_EQUATION_RE = re.compile(r"([A-Za-z0-9()\[\]{}·.\s+]+(?:->|=|→|⟶|⇌|⇋)[A-Za-z0-9()\[\]{}·.\s+]+)")
_CONVERT_RE = re.compile(
    r"(?:convert\s+)?([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*"
    r"([A-Za-zµμΩ°/^*\d.·]+?)\s+(?:to|into|in)\s+"
    r"([A-Za-zµμΩ°/^*\d.·]+)",
    re.IGNORECASE,
)
# Natural-language unit queries:
# "How many metres are there in 3 miles?"
_HOW_MANY_IN_RE = re.compile(
    r"\bhow\s+many\s+([A-Za-zµμΩ°/^*\d.·]+)\s+(?:are\s+)?(?:there\s+)?in\s+"
    r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([A-Za-zµμΩ°/^*\d.·]+)",
    re.IGNORECASE,
)
# Contextual unit queries:
# "A recipe needs 350 g of flour. How many ounces is that?"
_CONTEXT_HOW_MANY_RE = re.compile(
    r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([A-Za-zµμΩ°/^*\d.·]+)\b"
    r".*?\bhow\s+many\s+([A-Za-zµμΩ°/^*\d.·]+)\s+(?:is|are)\s+(?:that|it|this)\b",
    re.IGNORECASE | re.DOTALL,
)


def _new_step(
    steps: list[SolutionStep], description: str, result: str = "", expression: str = ""
) -> None:
    steps.append(
        SolutionStep(
            n=len(steps) + 1, description=description, expression=expression, result=result
        )
    )


# ---------------------------------------------------------------------------
# Mathematics (sympy)
# ---------------------------------------------------------------------------


def _pick_symbol(expr):
    import sympy

    symbols = sorted(expr.free_symbols, key=lambda s: s.name)
    for symbol in symbols:
        if symbol.name == "x":
            return symbol
    return symbols[0] if symbols else sympy.Symbol("x")


def _sympify(
    text: str,
    *,
    bound_symbolic_degree: bool = False,
    max_symbolic_degree: int | None = None,
):
    from olivia.tools.science import safe_sympify

    # Numeric magnitude, combinatorial, and eager-operation bounds run directly
    # on safe_sympify's validated AST before compile/eval. Symbolic degree
    # limits apply only where explicitly requested (solve/roots/expand/factor).
    return safe_sympify(
        text,
        implicit_multiplication=True,
        bound_symbolic_degree=bound_symbolic_degree,
        max_symbolic_degree=max_symbolic_degree,
    )


def _safe_str(obj: object, expression: str) -> str:
    """Stringify a symbolic value inside the typed failure path (guards int->str limit)."""
    try:
        return str(obj)
    except ValueError as exc:
        raise SolverParseError(
            f"result too large to display: {expression}", expression=expression
        ) from exc


def _solve_math(problem: str) -> WorkedSolution | None:
    try:
        import sympy
    except ImportError:
        return None
    text = problem.strip()

    # Equations and systems, in any notation: "solve 2x + y = 10, x - y = 2",
    # "the system ... and ...", "x² − 5x + 6 = 0", "2*x + 3 = 7".  Prose is left
    # to the branches below ("If f(x) = ..., what is f'(x)?").
    solution = solve_equations(problem)
    if solution is not None:
        return solution

    # Derivative: "differentiate x^3 + 2x" or "derivative of x^3" or "d/dx x^3"
    # Integrate: "integrate 2*x" or "integral of 1/x"
    for pattern, op, verb in (
        (_DERIV_RE, "diff", "Differentiate"),
        (_INTEGRATE_RE, "integrate", "Integrate"),
    ):
        match = pattern.search(text)
        if match:
            raw_expr = match.group(1).strip()
            try:
                expr = _sympify(raw_expr)
                var = _pick_symbol(expr)
                respect = _WITH_RESPECT_RE.search(text)
                if respect and sympy.Symbol(respect.group(1)) in expr.free_symbols:
                    var = sympy.Symbol(respect.group(1))
                result = sympy.diff(expr, var) if op == "diff" else sympy.integrate(expr, var)
                expr_str = _safe_str(expr, raw_expr)
                result_str = _safe_str(result, raw_expr)
            except _parse_errors() as exc:
                logger.exception("%s: cannot parse expression %r", verb, raw_expr)
                raise SolverParseError(
                    f"cannot parse expression for {verb.lower()}: {raw_expr}",
                    expression=raw_expr,
                ) from exc
            steps: list[SolutionStep] = []
            symbol = "+ C" if op == "integrate" else ""
            _new_step(steps, f"{verb} with respect to {var}", expr_str)
            _new_step(steps, "Apply the rules", f"{result_str} {symbol}".strip())
            return WorkedSolution(
                problem=problem,
                subject="math",
                steps=steps,
                final_answer=f"{result_str} {symbol}".strip(),
                method="symbolic",
                confidence=0.9,
            )

    # Function notation: "If f(x) = 3x^2 + 2x, what is f'(x)?"
    match = _FUNCT_DERIV_RE.search(text)
    if match:
        var_name, expr_text, respect_var = (
            match.group(1),
            match.group(2).strip(),
            match.group(3),
        )
        try:
            expr = _sympify(expr_text)
            var = (
                sympy.Symbol(respect_var)
                if respect_var in [str(s) for s in expr.free_symbols]
                else _pick_symbol(expr)
            )
            result = sympy.diff(expr, var)
            expr_str = _safe_str(expr, expr_text)
            result_str = _safe_str(result, expr_text)
        except _parse_errors() as exc:
            logger.exception("derivative: cannot parse function %r", expr_text)
            raise SolverParseError(
                f"cannot parse function for derivative: {expr_text}",
                expression=expr_text,
            ) from exc
        steps = []
        _new_step(steps, f"Given f({var_name}) = {expr_text}", f"f({var_name}) = {expr_str}")
        _new_step(steps, f"Differentiate with respect to {var}", f"f'({var_name}) = {result_str}")
        return WorkedSolution(
            problem=problem,
            subject="math",
            steps=steps,
            final_answer=result_str,
            method="symbolic",
            confidence=0.9,
        )

    # "Find the roots of x^2 - 7x + 12"
    match = _FIND_ROOTS_RE.search(text)
    if match:
        raw_expr = match.group(1).strip()
        try:
            expr = _sympify(raw_expr, bound_symbolic_degree=True)
            var = _pick_symbol(expr)
            roots = sympy.solve(expr, var)
            expr_str = _safe_str(expr, raw_expr)
            factored = sympy.factor(expr)
            factored_str = _safe_str(factored, raw_expr) if factored != sympy.expand(expr) else None
            answer = (
                ", ".join(f"{var} = {_safe_str(sympy.nsimplify(r), raw_expr)}" for r in roots)
                or "no solution"
            )
        except _parse_errors() as exc:
            logger.exception("find roots: cannot parse expression %r", raw_expr)
            raise SolverParseError(
                f"cannot parse expression for roots: {raw_expr}",
                expression=raw_expr,
            ) from exc
        steps = []
        _new_step(steps, "Set expression equal to zero", f"{expr_str} = 0")
        if factored_str is not None:
            _new_step(steps, "Factor", f"{factored_str} = 0")
        _new_step(steps, f"Solve for {var}", answer)
        return WorkedSolution(
            problem=problem,
            subject="math",
            steps=steps,
            final_answer=answer,
            method="symbolic",
            confidence=0.9,
        )

    # Percentage: "What is 15% of 240?"
    match = _PERCENT_RE.search(text)
    if match:
        percent = float(match.group(1))
        value = float(match.group(2))
        result = percent / 100 * value
        steps = []
        _new_step(steps, f"Convert {percent}% to decimal", f"{percent / 100}")
        _new_step(steps, f"Multiply by {value}", f"{percent / 100} × {value} = {result}")
        return WorkedSolution(
            problem=problem,
            subject="math",
            steps=steps,
            final_answer=str(result),
            method="symbolic",
            confidence=0.95,
        )

    # Sum of integers: "What is the sum of the first 100 positive integers?"
    match = _SUM_INTEGERS_RE.search(text)
    if match:
        n = int(match.group(1))
        result = n * (n + 1) // 2
        steps = []
        _new_step(steps, f"Sum of first {n} positive integers", f"n(n+1)/2 = {n}×{n + 1}/2")
        _new_step(steps, "Calculate", f"{n}×{n + 1}/2 = {result}")
        return WorkedSolution(
            problem=problem,
            subject="math",
            steps=steps,
            final_answer=str(result),
            method="symbolic",
            confidence=0.95,
        )

    # Limit: "Evaluate the limit of sin(x)/x as x approaches 0"
    match = _LIMIT_RE.search(text)
    if match:
        expr_text = match.group(1).strip()
        var_name = match.group(2)
        limit_val = match.group(3)
        try:
            expr = _sympify(expr_text)
            var = sympy.Symbol(var_name)
            limit_point = sympy.sympify(limit_val)
            result = sympy.limit(expr, var, limit_point)
            expr_str = _safe_str(expr, expr_text)
            result_str = _safe_str(result, expr_text)
        except _parse_errors() as exc:
            logger.exception("limit: cannot parse expression %r", expr_text)
            raise SolverParseError(
                f"cannot parse limit expression: {expr_text}",
                expression=expr_text,
            ) from exc
        steps = []
        _new_step(
            steps,
            f"Limit of {expr_text} as {var_name} → {limit_val}",
            f"lim_{{x→{limit_val}}} {expr_str}",
        )
        _new_step(steps, "Evaluate", result_str)
        return WorkedSolution(
            problem=problem,
            subject="math",
            steps=steps,
            final_answer=result_str,
            method="symbolic",
            confidence=0.9,
        )

    # Fraction to decimal: "Convert the fraction 3/8 to a decimal"
    match = _FRACTION_DECIMAL_RE.search(text)
    if match:
        num = int(match.group(1))
        den = int(match.group(2))
        if den == 0:
            raise SolverParseError("division by zero", expression=f"{num}/{den}")
        result = num / den
        steps = []
        _new_step(steps, f"Divide {num} by {den}", f"{num}/{den} = {result}")
        return WorkedSolution(
            problem=problem,
            subject="math",
            steps=steps,
            final_answer=str(result),
            method="symbolic",
            confidence=0.95,
        )

    # Word problem: rectangle area from perimeter
    match = _RECTANGLE_WORD_RE.search(text)
    if match:
        perimeter = float(match.group(1))
        width = perimeter / 6
        length = perimeter / 3
        area = length * width
        steps = []
        _new_step(steps, f"Perimeter = 2(length + width) = {perimeter}", "length = 2 × width")
        _new_step(
            steps, "Substitute: 2(2w + w) = 6w = perimeter", f"width = {perimeter}/6 = {width}"
        )
        _new_step(steps, "Length = 2 × width", f"length = {length}")
        _new_step(steps, "Area = length × width", f"{length} × {width} = {area}")
        return WorkedSolution(
            problem=problem,
            subject="math",
            steps=steps,
            final_answer=f"{area}",
            method="symbolic",
            confidence=0.9,
        )

    for pattern, fn_name, verb in (
        (_SIMPLIFY_RE, "simplify", "Simplify"),
        (_FACTOR_RE, "factor", "Factor"),
        (_EXPAND_RE, "expand", "Expand"),
    ):
        match = pattern.search(text)
        if match:
            raw_expr = match.group(1).strip()
            try:
                max_deg = 256 if fn_name in ("expand", "factor") else None
                expr = _sympify(raw_expr, max_symbolic_degree=max_deg)
                result = getattr(sympy, fn_name)(expr)
                expr_str = _safe_str(expr, raw_expr)
                result_str = _safe_str(result, raw_expr)
            except _parse_errors() as exc:
                logger.exception("%s: cannot parse expression %r", verb, raw_expr)
                raise SolverParseError(
                    f"cannot parse expression for {verb.lower()}: {raw_expr}",
                    expression=raw_expr,
                ) from exc
            steps = []
            _new_step(steps, "Start from", expr_str)
            _new_step(steps, verb, result_str)
            return WorkedSolution(
                problem=problem,
                subject="math",
                steps=steps,
                final_answer=result_str,
                method="symbolic",
                confidence=0.9,
            )

    return _evaluate_arithmetic(problem, text)


def _evaluate_arithmetic(problem: str, text: str) -> WorkedSolution | None:
    import sympy

    match = _EVAL_RE.search(text)
    candidate = match.group(1).strip() if match else text.strip().rstrip(".?")
    normalised = candidate.replace("^", "**")
    if not _ARITH_RE.match(candidate) or not re.search(r"[-+*/]", candidate):
        return None
    try:
        expr = _sympify(normalised)
    except _parse_errors() as exc:
        logger.exception("evaluate: cannot parse arithmetic %r", normalised)
        raise SolverParseError(
            f"cannot parse arithmetic expression: {normalised}", expression=normalised
        ) from exc
    if expr.free_symbols:
        return None
    try:
        value = expr if expr.is_Rational else sympy.N(expr)
        expr_str = f"{expr}"
        value_str = f"{value}"
    except ValueError as exc:
        if "integer string conversion" not in str(exc):
            raise
        raise SolverParseError(
            f"result too large to display: {normalised}", expression=normalised
        ) from exc
    steps: list[SolutionStep] = []
    _new_step(steps, "Evaluate the expression", f"{expr_str} = {value_str}")
    return WorkedSolution(
        problem=problem,
        subject="math",
        steps=steps,
        final_answer=value_str,
        method="symbolic",
        confidence=0.85,
    )


# ---------------------------------------------------------------------------
# Chemistry
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "of",
    "the",
    "for",
    "and",
    "mass",
    "molar",
    "weight",
    "molecular",
    "formula",
    "compound",
    "what",
    "is",
    "balance",
    "calculate",
}


def _extract_formula(text: str) -> str | None:
    from olivia.tools.chemistry import parse_formula

    for token in _FORMULA_TOKEN_RE.findall(text):
        if token.lower() in _STOPWORDS or not re.search(r"[A-Z]", token):
            continue
        if parse_formula(token):
            return token
    return None


def _solve_chemistry(problem: str) -> WorkedSolution | None:
    from olivia.tools.chemistry import ELEMENTS, balance_equation, molar_mass

    if _MOLAR_RE.search(problem):
        formula = _extract_formula(problem)
        if formula:
            result = molar_mass(formula)
            if result["ok"]:
                steps: list[SolutionStep] = []
                for item in result["breakdown"]:
                    weight = ELEMENTS[item["element"]][1]
                    _new_step(
                        steps,
                        f"{item['count']} × {item['element']} ({weight:g} g/mol)",
                        f"{item['mass']:g} g/mol",
                    )
                _new_step(steps, "Sum the atomic masses", f"{result['molar_mass']:g} g/mol")
                return WorkedSolution(
                    problem=problem,
                    subject="chemistry",
                    steps=steps,
                    final_answer=f"{result['molar_mass']:g} g/mol",
                    method="chemistry",
                    confidence=0.95,
                )

    if "balance" in problem.lower():
        stripped = re.sub(r"(?i)\bbalance(?:\s+the)?(?:\s+equation)?\s*:?\s*", "", problem, count=1)
        match = _EQUATION_RE.search(stripped)
        if match:
            result = balance_equation(match.group(1).strip())
            if result.get("ok"):
                steps = []
                _new_step(steps, "Unbalanced equation", match.group(1).strip())
                _new_step(steps, "Conserve atoms of every element", result["balanced"])
                return WorkedSolution(
                    problem=problem,
                    subject="chemistry",
                    steps=steps,
                    final_answer=result["balanced"],
                    method="chemistry",
                    confidence=0.9,
                )

    from olivia.study.chemistry_solver import solve_chemistry_problem

    return solve_chemistry_problem(problem)


# ---------------------------------------------------------------------------
# Physics and units
# ---------------------------------------------------------------------------


def _fmt_value(value: float) -> str:
    """Plain integer for whole numbers, ``repr`` (full precision) otherwise."""
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e16:
        return str(int(value))
    return repr(value)


def _solve_physics(problem: str) -> WorkedSolution | None:
    from olivia.study.physics_solver import solve_physics_problem
    from olivia.tools.physics import physical_constant

    result = physical_constant(problem)
    if result.get("ok"):
        unit = f" {result['unit']}" if result["unit"] else ""
        value = f"{_fmt_value(result['value'])}{unit}"
        steps: list[SolutionStep] = []
        _new_step(steps, f"Look up the {result['name']}", f"{result['symbol']} = {value}")
        return WorkedSolution(
            problem=problem,
            subject="physics",
            steps=steps,
            final_answer=value,
            method="physics",
            confidence=0.9,
        )
    return solve_physics_problem(problem)


def _extract_unit_conversion(problem: str) -> tuple[float, str, str] | None:
    """Extract (value, from_unit, to_unit) from direct or natural-language unit queries."""
    match = _CONVERT_RE.search(problem)
    if match:
        return float(match.group(1)), match.group(2).strip(" .?"), match.group(3).strip(" .?")
    match = _HOW_MANY_IN_RE.search(problem)
    if match:
        return float(match.group(2)), match.group(3).strip(" .?"), match.group(1).strip(" .?")
    match = _CONTEXT_HOW_MANY_RE.search(problem)
    if match:
        return float(match.group(1)), match.group(2).strip(" .?"), match.group(3).strip(" .?")
    return None


def _solve_units(problem: str) -> WorkedSolution | None:
    from olivia.tools.units import convert_units

    extracted = _extract_unit_conversion(problem)
    if extracted is None:
        return None
    value, from_unit, to_unit = extracted
    if not math.isfinite(value):
        return None
    result = convert_units(value, from_unit, to_unit)
    if not result["ok"]:
        return None
    steps: list[SolutionStep] = []
    _new_step(
        steps, f"Convert {value:g} {from_unit} to {to_unit}", f"{result['value']:.6g} {to_unit}"
    )
    return WorkedSolution(
        problem=problem,
        subject="units",
        steps=steps,
        final_answer=f"{result['value']:.6g} {to_unit}",
        method="units",
        confidence=0.9,
    )


# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------


def _solve_llm(problem: str, subject: str, client: LLMClient) -> WorkedSolution | None:
    prompt = (
        f"Solve this {subject} problem step by step: {problem}\n\n"
        'Respond as JSON: {"steps": [{"description": str, "result": str}], '
        '"answer": str}. One operation per step; keep results exact.'
    )
    payload = ask_json(client, prompt, system=SOLVER_SYSTEM, max_tokens=2000)
    if not isinstance(payload, dict) or not isinstance(payload.get("steps"), list):
        return None
    steps: list[SolutionStep] = []
    for item in payload["steps"]:
        if isinstance(item, dict) and str(item.get("description", "")).strip():
            _new_step(steps, str(item["description"]).strip(), str(item.get("result", "")).strip())
    if not steps:
        return None
    answer = str(payload.get("answer", "")).strip()
    if not answer:
        return None
    return WorkedSolution(
        problem=problem,
        subject=subject,
        steps=steps,
        final_answer=answer,
        method="llm",
        confidence=0.7,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_MATH_HINTS = (
    "solve",
    "differentiate",
    "derivative",
    "integrate",
    "integral",
    "simplify",
    "factor",
    "expand",
    "equation",
    "calculate",
    "evaluate",
)
_CHEM_HINTS = (
    "molar mass",
    "molecular weight",
    "balance",
    "mole",
    "reaction",
    "compound",
    "chemical",
)
_PHYS_HINTS = (
    "constant",
    "speed of light",
    "planck",
    "avogadro",
    "boltzmann",
    "gravitational",
    "permittivity",
    "permeability",
)
_UNIT_HINTS = ("convert", " to ", " in ", "how many")


def _classify(problem: str) -> str:
    low = problem.lower()
    for subject, hints in (
        ("chemistry", _CHEM_HINTS),
        ("physics", _PHYS_HINTS),
        ("math", _MATH_HINTS),
        ("units", _UNIT_HINTS),
    ):
        if any(hint in low for hint in hints):
            return subject
    return "general"


_SOLVERS = {
    "math": _solve_math,
    "chemistry": _solve_chemistry,
    "physics": _solve_physics,
    "units": _solve_units,
}


def solve_problem(
    problem: str,
    subject: str = "auto",
    client: LLMClient | None = None,
) -> WorkedSolution:
    """Return a step-by-step ``WorkedSolution`` for a STEM ``problem``."""
    problem = problem.strip()
    client = client or get_client()

    if subject in _SOLVERS:
        attempts = [_SOLVERS[subject]]
    else:  # 'auto' — try every deterministic solver in turn
        attempts = [_solve_math, _solve_chemistry, _solve_physics, _solve_units]

    for attempt in attempts:
        try:
            solution = attempt(problem)
        except OliviaError as exc:  # matched intent, broken expression: surfaced, not "no match"
            logger.warning("solver %s parse error: %s", attempt.__name__, exc)
            solution = None
        except Exception as exc:  # a solver bug must not sink the whole call
            logger.debug("solver %s failed: %s", attempt.__name__, exc)
            solution = None
        if solution is not None:
            return solution

    label = subject if subject != "auto" else _classify(problem)
    if client.available:
        solution = _solve_llm(problem, label, client)
        if solution is not None:
            return solution

    return WorkedSolution(
        problem=problem,
        subject=label,
        method="none",
        confidence=0.0,
        steps=[
            SolutionStep(
                n=1,
                description="No symbolic method matched this problem and no language-model "
                "answer was available, so it cannot be solved offline.",
            )
        ],
    )


def solution_to_markdown(solution: WorkedSolution) -> str:
    """Render a WorkedSolution as readable step-by-step markdown."""
    lines = [f"**Problem:** {solution.problem}", ""]
    for step in solution.steps:
        detail = f"{step.description}"
        if step.result:
            detail += f" -> `{step.result}`"
        lines.append(f"{step.n}. {detail}")
    if solution.final_answer:
        lines += ["", f"**Answer:** {solution.final_answer}"]
    method = {
        "symbolic": "computed symbolically (sympy)",
        "chemistry": "computed from the periodic table",
        "physics": "looked up (CODATA constants)",
        "units": "converted by dimensional analysis",
        "llm": "reasoned by the language model",
        "none": "unsolved",
    }.get(solution.method, solution.method)
    lines += ["", f"*Method: {method}.*"]
    return "\n".join(lines)
