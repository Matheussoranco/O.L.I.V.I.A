"""Step-by-step STEM solver — GPAI-style worked solutions, symbolic-first.

``solve_problem`` routes a problem to a deterministic solver (sympy for maths,
the chemistry/physics/units tools for the sciences) and returns an ordered
``WorkedSolution`` — the work, not just the answer.  Only when no symbolic
method fits does it fall back to a structured-JSON LLM call, and if there is no
backend it says so honestly (confidence 0), never fabricating steps.
"""

from __future__ import annotations

import logging
import re

from olivia.core.records import SolutionStep, WorkedSolution
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import SOLVER_SYSTEM
from olivia.llm.structured import ask_json

logger = logging.getLogger(__name__)

# ── Maths intent patterns ───────────────────────────────────────────────────
_SOLVE_RE = re.compile(
    r"\bsolve\b[^:]*?:?\s*(.+?)\s*=\s*(.+?)(?:\s+for\s+\w+)?\s*[.?]?\s*$", re.IGNORECASE
)
_DERIV_RE = re.compile(
    r"\b(?:differentiate|derivative of|d/dx)\b\s*:?\s*(.+?)\s*[.?]?\s*$", re.IGNORECASE
)
_INTEGRATE_RE = re.compile(
    r"\bintegra(?:te|l of)\b\s*:?\s*(.+?)\s*(?:\bdx\b)?\s*[.?]?\s*$", re.IGNORECASE
)
_SIMPLIFY_RE = re.compile(r"\bsimplify\b\s*:?\s*(.+?)\s*[.?]?\s*$", re.IGNORECASE)
_FACTOR_RE = re.compile(r"\bfactor\b\s*:?\s*(.+?)\s*[.?]?\s*$", re.IGNORECASE)
_EXPAND_RE = re.compile(r"\bexpand\b\s*:?\s*(.+?)\s*[.?]?\s*$", re.IGNORECASE)
_EVAL_RE = re.compile(
    r"\b(?:what is|calculate|compute|evaluate)\b\s*:?\s*(.+?)\s*[.?]?\s*$", re.IGNORECASE
)
_ARITH_RE = re.compile(r"^[0-9+\-*/^().\s]+$")

# ── Chemistry / units intent patterns ───────────────────────────────────────
_MOLAR_RE = re.compile(
    r"molar mass|molecular (?:weight|mass)|formula weight|molar weight", re.IGNORECASE
)
_FORMULA_TOKEN_RE = re.compile(r"[A-Za-z0-9()\[\]{}·.]+")
_EQUATION_RE = re.compile(r"([A-Za-z0-9()\[\]{}·.\s+]+(?:->|=|→|⟶)[A-Za-z0-9()\[\]{}·.\s+]+)")
_CONVERT_RE = re.compile(
    r"(?:convert\s+)?(-?\d+\.?\d*)\s*([A-Za-zµμΩ°/^*\d.·]+?)\s+(?:to|into|in)\s+"
    r"([A-Za-zµμΩ°/^*\d.·]+)",
    re.IGNORECASE,
)


def _new_step(steps: list[SolutionStep], description: str, result: str = "",
              expression: str = "") -> None:
    steps.append(SolutionStep(n=len(steps) + 1, description=description,
                              expression=expression, result=result))


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


def _sympify(text: str):
    import sympy

    return sympy.sympify(text.replace("^", "**"))


def _solve_math(problem: str) -> WorkedSolution | None:
    try:
        import sympy
    except ImportError:
        return None
    text = problem.strip()

    match = _SOLVE_RE.search(text)
    if match:
        lhs, rhs = match.group(1).strip(), match.group(2).strip()
        try:
            expr = _sympify(f"({lhs})-({rhs})")
            var = _pick_symbol(expr)
            roots = sympy.solve(expr, var)
        except Exception:
            return None
        steps: list[SolutionStep] = []
        _new_step(steps, "Restate the equation", f"{lhs} = {rhs}")
        moved = sympy.simplify(expr)
        _new_step(steps, "Move every term to one side", f"{moved} = 0")
        factored = sympy.factor(expr)
        if factored != sympy.expand(expr):
            _new_step(steps, "Factor", f"{factored} = 0")
        answer = ", ".join(f"{var} = {sympy.nsimplify(r)}" for r in roots) or "no solution"
        _new_step(steps, f"Solve for {var}", answer)
        return WorkedSolution(problem=problem, subject="math", steps=steps,
                              final_answer=answer, method="symbolic", confidence=0.9)

    for pattern, op, verb in (
        (_DERIV_RE, "diff", "Differentiate"),
        (_INTEGRATE_RE, "integrate", "Integrate"),
    ):
        match = pattern.search(text)
        if match:
            try:
                expr = _sympify(match.group(1).strip())
                var = _pick_symbol(expr)
                result = sympy.diff(expr, var) if op == "diff" else sympy.integrate(expr, var)
            except Exception:
                return None
            steps = []
            symbol = "+ C" if op == "integrate" else ""
            _new_step(steps, f"{verb} with respect to {var}", f"{expr}")
            _new_step(steps, "Apply the rules", f"{result} {symbol}".strip())
            return WorkedSolution(problem=problem, subject="math", steps=steps,
                                  final_answer=f"{result} {symbol}".strip(),
                                  method="symbolic", confidence=0.9)

    for pattern, fn_name, verb in (
        (_SIMPLIFY_RE, "simplify", "Simplify"),
        (_FACTOR_RE, "factor", "Factor"),
        (_EXPAND_RE, "expand", "Expand"),
    ):
        match = pattern.search(text)
        if match:
            try:
                expr = _sympify(match.group(1).strip())
                result = getattr(sympy, fn_name)(expr)
            except Exception:
                return None
            steps = []
            _new_step(steps, "Start from", f"{expr}")
            _new_step(steps, verb, f"{result}")
            return WorkedSolution(problem=problem, subject="math", steps=steps,
                                  final_answer=f"{result}", method="symbolic", confidence=0.9)

    return _evaluate_arithmetic(problem, text)


def _evaluate_arithmetic(problem: str, text: str) -> WorkedSolution | None:
    import sympy

    match = _EVAL_RE.search(text)
    candidate = match.group(1).strip() if match else text.strip().rstrip(".?")
    normalised = candidate.replace("^", "**")
    if not _ARITH_RE.match(candidate) or not re.search(r"[-+*/]", candidate):
        return None
    try:
        expr = sympy.sympify(normalised)
    except Exception:
        return None
    if expr.free_symbols:
        return None
    value = expr if expr.is_Rational else sympy.N(expr)
    steps: list[SolutionStep] = []
    _new_step(steps, "Evaluate the expression", f"{expr} = {value}")
    return WorkedSolution(problem=problem, subject="math", steps=steps,
                          final_answer=f"{value}", method="symbolic", confidence=0.85)


# ---------------------------------------------------------------------------
# Chemistry
# ---------------------------------------------------------------------------

_STOPWORDS = {"of", "the", "for", "and", "mass", "molar", "weight", "molecular",
              "formula", "compound", "what", "is", "balance", "calculate"}


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
                _new_step(steps, "Sum the atomic masses",
                          f"{result['molar_mass']:g} g/mol")
                return WorkedSolution(
                    problem=problem, subject="chemistry", steps=steps,
                    final_answer=f"{result['molar_mass']:g} g/mol",
                    method="chemistry", confidence=0.95,
                )

    if "balance" in problem.lower():
        stripped = re.sub(
            r"(?i)\bbalance(?:\s+the)?(?:\s+equation)?\s*:?\s*", "", problem, count=1
        )
        match = _EQUATION_RE.search(stripped)
        if match:
            result = balance_equation(match.group(1).strip())
            if result.get("ok"):
                steps = []
                _new_step(steps, "Unbalanced equation", match.group(1).strip())
                _new_step(steps, "Conserve atoms of every element",
                          result["balanced"])
                return WorkedSolution(
                    problem=problem, subject="chemistry", steps=steps,
                    final_answer=result["balanced"], method="chemistry", confidence=0.9,
                )
    return None


# ---------------------------------------------------------------------------
# Physics and units
# ---------------------------------------------------------------------------


def _fmt_value(value: float) -> str:
    """Plain integer for whole numbers, ``repr`` (full precision) otherwise."""
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e16:
        return str(int(value))
    return repr(value)


def _solve_physics(problem: str) -> WorkedSolution | None:
    from olivia.tools.physics import physical_constant

    result = physical_constant(problem)
    if not result.get("ok"):
        return None
    unit = f" {result['unit']}" if result["unit"] else ""
    value = f"{_fmt_value(result['value'])}{unit}"
    steps: list[SolutionStep] = []
    _new_step(steps, f"Look up the {result['name']}", f"{result['symbol']} = {value}")
    return WorkedSolution(
        problem=problem, subject="physics", steps=steps,
        final_answer=value, method="physics", confidence=0.9,
    )


def _solve_units(problem: str) -> WorkedSolution | None:
    from olivia.tools.units import convert_units

    match = _CONVERT_RE.search(problem)
    if not match:
        return None
    value = float(match.group(1))
    from_unit, to_unit = match.group(2).strip(" ."), match.group(3).strip(" .")
    result = convert_units(value, from_unit, to_unit)
    if not result["ok"]:
        return None
    steps: list[SolutionStep] = []
    _new_step(steps, f"Convert {value:g} {from_unit} to {to_unit}",
              f"{result['value']:.6g} {to_unit}")
    return WorkedSolution(
        problem=problem, subject="units", steps=steps,
        final_answer=f"{result['value']:.6g} {to_unit}", method="units", confidence=0.9,
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
            _new_step(steps, str(item["description"]).strip(),
                      str(item.get("result", "")).strip())
    if not steps:
        return None
    return WorkedSolution(problem=problem, subject=subject, steps=steps,
                          final_answer=str(payload.get("answer", "")).strip(),
                          method="llm", confidence=0.7)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_MATH_HINTS = ("solve", "differentiate", "derivative", "integrate", "integral",
               "simplify", "factor", "expand", "equation", "calculate", "evaluate")
_CHEM_HINTS = ("molar mass", "molecular weight", "balance", "mole", "reaction",
               "compound", "chemical")
_PHYS_HINTS = ("constant", "speed of light", "planck", "avogadro", "boltzmann",
               "gravitational", "permittivity", "permeability")
_UNIT_HINTS = ("convert", " to ", " in ", "how many")


def _classify(problem: str) -> str:
    low = problem.lower()
    for subject, hints in (("chemistry", _CHEM_HINTS), ("physics", _PHYS_HINTS),
                           ("math", _MATH_HINTS), ("units", _UNIT_HINTS)):
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
        problem=problem, subject=label, method="none", confidence=0.0,
        steps=[SolutionStep(
            n=1,
            description="No symbolic method matched this problem and no LLM "
            "backend is configured, so it cannot be solved offline.",
        )],
    )


def solution_to_markdown(solution: WorkedSolution) -> str:
    """Render a WorkedSolution as readable step-by-step markdown."""
    lines = [f"**Problem:** {solution.problem}", ""]
    for step in solution.steps:
        detail = f"{step.description}"
        if step.result:
            detail += f" → `{step.result}`"
        lines.append(f"{step.n}. {detail}")
    if solution.final_answer:
        lines += ["", f"**Answer:** {solution.final_answer}"]
    method = {"symbolic": "computed symbolically (sympy)",
              "chemistry": "computed from the periodic table",
              "physics": "looked up (CODATA constants)",
              "units": "converted by dimensional analysis",
              "llm": "reasoned by the language model",
              "none": "unsolved"}.get(solution.method, solution.method)
    lines += ["", f"*Method: {method}.*"]
    return "\n".join(lines)
