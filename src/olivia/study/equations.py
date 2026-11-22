"""Equations as people write them → worked symbolic solutions.

``solve_equations`` is the single entry point the solver uses for anything that
is an equation or a system of equations.  It owns the whole path:

1. **Notation** — Unicode maths (``x²``, ``−``, ``×``, ``÷``, ``√``, ``π``),
   caret powers, ``==`` and indexed unknowns (``x1`` → ``x_1``) are rewritten to
   the ASCII form ``safe_sympify`` accepts.
2. **Instruction** — ``solve``, ``the system``, ``solve for x and y:`` and a
   trailing ``for t`` are stripped; requested unknowns are remembered.
3. **Splitting** — equations are separated on top-level ``,`` ``;`` newlines
   and ``and``; commas inside brackets (``log(x, 2)``) are left alone.
4. **Prose guard** — every identifier must be a variable, a known function or
   constant, or a juxtaposition of variables used elsewhere (``xy``).  Without
   this, implicit multiplication reads ``the value 2x = 4`` as
   ``t*h*e*v*a*l*u*e*2*x = 4`` and "solves" it confidently and wrongly.
5. **Solving** — sympy, with worked steps: elimination for square linear
   systems, discriminant for quadratics, and a substitution check of every
   reported solution.

Contract with ``solve_problem``: return ``None`` when the text is not an
equation problem (another solver may own it); raise ``SolverParseError`` when it
clearly *is* one — an explicit instruction, or nothing but maths — and the
expression is broken; otherwise return a ``WorkedSolution``.
"""

from __future__ import annotations

import ast
import logging
import math
import re
from dataclasses import dataclass
from functools import lru_cache

from olivia.core.errors import SolverParseError
from olivia.core.records import SolutionStep, WorkedSolution

logger = logging.getLogger(__name__)

MAX_EQUATIONS = 8
"""More equations than this is not a study problem; refuse rather than grind."""

MAX_EXPONENT = 64
"""Largest power of an *unknown* accepted: ``x^1000000 = 1`` would make
``sympy.solve`` build a million roots."""

MAX_RESULT_DIGITS = 1000
"""Largest *number* an expression may denote.  sympy evaluates ``Integer **
Integer`` the moment text is parsed, so ``2^3^20`` (= 2^3486784401) stalls inside
sympify and ``2^2^2^2^2`` (19 729 digits) later trips Python's int→str limit.
Both are refused structurally, before any evaluation (``_check_growth``)."""

MAX_COMBINATORIAL_ARGUMENT = 1000
"""``factorial``/``fibonacci``/… evaluate eagerly; larger arguments are refused."""

MAX_ELIMINATION_UNKNOWNS = 4
"""Show row-by-row elimination up to this size; larger systems get a summary."""

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Equation:
    """One equation, both sides already in ``safe_sympify`` notation."""

    lhs: str
    rhs: str

    def __str__(self) -> str:
        return f"{self.lhs} = {self.rhs}"


@dataclass(frozen=True)
class EquationProblem:
    """What the user asked: equations, plus unknowns if they named any."""

    equations: tuple[Equation, ...]
    unknowns: tuple[str, ...] = ()
    explicit: bool = False
    """True when an instruction (``solve``/``the system``) introduced it."""

    def describe(self) -> str:
        return ", ".join(str(eq) for eq in self.equations)


# ---------------------------------------------------------------------------
# 1. Notation
# ---------------------------------------------------------------------------

_CHAR_MAP = str.maketrans(
    {
        "−": "-",  # minus sign
        "–": "-",  # en dash (pasted from word processors)
        "‒": "-",  # figure dash
        "﹣": "-",  # small hyphen-minus
        "－": "-",  # fullwidth hyphen-minus
        "＋": "+",  # fullwidth plus
        "×": "*",  # multiplication sign
        "⋅": "*",  # dot operator
        "·": "*",  # middle dot
        "∙": "*",  # bullet operator
        "∗": "*",  # asterisk operator
        "÷": "/",  # division sign
        "∕": "/",  # division slash
        "＝": "=",  # fullwidth equals
        "π": " pi ",
        " ": " ",
        " ": " ",
        " ": " ",
    }
)
_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
_SUPERSCRIPT_RUN = re.compile("[⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺]+")
_SQRT_RE = re.compile(r"√\s*(\(|\d+(?:\.\d+)?|[A-Za-z]\w*)")
_INEQUALITY_RE = re.compile(r"<|>|≤|≥|≠|!=")


def _superscript(match: re.Match[str]) -> str:
    power = match.group(0).translate(_SUPERSCRIPTS)
    return f"^{power}" if power.isdigit() else f"^({power})"


def _sqrt(match: re.Match[str]) -> str:
    operand = match.group(1)
    return "sqrt(" if operand == "(" else f"sqrt({operand})"


def normalise_notation(text: str) -> str:
    """Rewrite everyday/Unicode maths notation into ASCII sympy notation.

    ``**`` is left alone; ``^`` is kept because it reads better in worked
    steps and ``safe_sympify`` converts it.  ``==`` collapses to ``=``.
    """
    text = text.translate(_CHAR_MAP)
    text = _SUPERSCRIPT_RUN.sub(_superscript, text)
    text = _SQRT_RE.sub(_sqrt, text)
    text = text.replace("==", "=")
    return re.sub(r"[ \t]+", " ", text).strip()


# ---------------------------------------------------------------------------
# 2. Instruction and requested unknowns
# ---------------------------------------------------------------------------

_VARS = r"[A-Za-z]\w*(?:\s*(?:,|and|&)\s*[A-Za-z]\w*)*"
_INSTRUCTION_RE = re.compile(
    rf"""^\s*
    (?:please\s+)?
    (?P<verb>solve\b)?\s*
    (?P<noun>(?:the\s+)?(?:following\s+)?
        (?:(?:linear|simultaneous)\s+)?
        (?:system(?:\s+of\s+(?:(?:linear|simultaneous)\s+)?equations)?|equations?)\b)?
    \s*(?:for\s+(?P<pre_vars>{_VARS})\s*:)?
    \s*:?\s*""",
    re.IGNORECASE | re.VERBOSE,
)
_TRAILING_VARS_RE = re.compile(
    rf"\s*,?\s*(?:solving\s+|solve\s+)?for\s+(?P<post_vars>{_VARS})\s*$", re.IGNORECASE
)
_TRAILING_PUNCT_RE = re.compile(r"[\s.?!]+$")
_BRACES_RE = re.compile(r"^\{(.*)\}$", re.DOTALL)


def _split_vars(text: str | None) -> tuple[str, ...]:
    if not text:
        return ()
    names = re.split(r"\s*(?:,|\band\b|&)\s*", text.strip(), flags=re.IGNORECASE)
    return tuple(_canonical_name(name) for name in names if name)


# ---------------------------------------------------------------------------
# 3. Splitting into equations
# ---------------------------------------------------------------------------

_AND_RE = re.compile(r"\s+and\s+", re.IGNORECASE)


def _split_equations(body: str) -> list[str]:
    """Split on top-level ``,``/``;``/newline/``and`` — never inside brackets."""
    parts: list[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(body):
        char = body[i]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(depth - 1, 0)
        elif depth == 0:
            if char in ",;\n":
                parts.append(body[start:i])
                start = i = i + 1
                continue
            conj = _AND_RE.match(body, i)
            if conj:
                parts.append(body[start:i])
                start = i = conj.end()
                continue
        i += 1
    parts.append(body[start:])
    return [part.strip() for part in parts if part.strip()]


# ---------------------------------------------------------------------------
# 4. Tokens and the prose guard
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"(?P<space>\s+)"
    r"|(?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"
    r"|(?P<name>[A-Za-z][A-Za-z0-9]*(?:_\d+)?)"
    r"|(?P<op>\*\*|[-+*/^(),])"
)
_VARIABLE_RE = re.compile(r"[A-Za-z](?:_\d+)?")
_GREEK = frozenset(
    {
        "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
        "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron", "rho", "sigma",
        "tau", "upsilon", "phi", "chi", "psi", "omega",
    }
)  # fmt: skip
_CONSTANTS = frozenset({"pi", "E", "I", "oo"})


@lru_cache(maxsize=1)
def _function_names() -> frozenset[str]:
    import sympy.functions

    return frozenset(
        name
        for name, value in vars(sympy.functions).items()
        if not name.startswith("_") and callable(value)
    )


def _canonical_name(name: str) -> str:
    """``x1`` → ``x_1`` (``safe_sympify`` cannot split ``x1``); others unchanged."""
    match = re.fullmatch(r"([A-Za-z])(\d+)", name)
    return f"{match.group(1)}_{match.group(2)}" if match else name


def _tokenise(side: str) -> list[tuple[str, str]] | None:
    """Return ``(kind, text)`` tokens, or ``None`` if any character is not maths."""
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(side):
        match = _TOKEN_RE.match(side, pos)
        if not match:
            return None
        kind = match.lastgroup or ""
        text = match.group(0)
        if kind == "name":
            text = _canonical_name(text)
        tokens.append((kind, text))
        pos = match.end()
    return tokens


# ---------------------------------------------------------------------------
# Growth guard: bound every number *before* sympy evaluates anything
# ---------------------------------------------------------------------------

_NUMBER_CONSTRUCTORS = frozenset({"Integer", "Float", "Rational", "Number"})
_SYMBOLIC_CONSTRUCTORS = frozenset({"Symbol", "Function", "Dummy", "Wild"})
_NUMERIC_CONSTANTS = {"pi": 4.0, "E": 3.0, "e": 3.0, "I": 1.0, "oo": math.inf}
_COMBINATORIAL = frozenset(
    {
        "factorial", "factorial2", "subfactorial", "binomial", "fibonacci",
        "lucas", "tribonacci", "bell", "catalan", "partition", "harmonic",
        "bernoulli", "euler", "genocchi", "andre", "motzkin", "primepi",
        "multigamma", "ff", "rf",
    }
)  # fmt: skip


class _TooLarge(Exception):
    """The expression denotes a number or degree beyond the offline limits."""


@lru_cache(maxsize=1)
def _parser_context() -> tuple[dict, tuple]:
    """The namespace and transformations ``safe_sympify`` parses with."""
    import sympy
    from sympy.parsing.sympy_parser import (
        implicit_multiplication_application,
        standard_transformations,
    )

    # Exactly what ``from sympy import *`` binds (parse_expr's default), with no exec.
    namespace = {name: getattr(sympy, name) for name in sympy.__all__}
    return namespace, (*standard_transformations, implicit_multiplication_application)


def _magnitude(node: ast.AST) -> float | None:
    """Upper bound on ``|value|`` of a numeric subtree; ``None`` if symbolic.

    Walks the code sympy *would* evaluate, so the bound sees exactly what the
    evaluator would: right-associative towers, any parenthesis depth, unary
    signs, products in exponents.  Raises ``_TooLarge`` where evaluation would
    explode.  A numeric subtree whose size cannot be bounded is ``inf``.
    """
    if isinstance(node, ast.Expression):
        return _magnitude(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float, str)):
            return None
        try:
            return abs(float(node.value))
        except ValueError:
            return None
    if isinstance(node, ast.Name):
        return _NUMERIC_CONSTANTS.get(node.id)
    if isinstance(node, ast.UnaryOp):
        return _magnitude(node.operand)
    if isinstance(node, ast.BinOp):
        return _binop_magnitude(node)
    if isinstance(node, ast.Call):
        return _call_magnitude(node)
    for child in ast.iter_child_nodes(node):  # anything else: still inspect inside
        _magnitude(child)
    return None


def _binop_magnitude(node: ast.BinOp) -> float | None:
    left, right = _magnitude(node.left), _magnitude(node.right)
    if isinstance(node.op, ast.Pow):
        if right is None:
            return None  # symbolic exponent (2^x): sympy cannot evaluate it
        if left is None:
            if right > MAX_EXPONENT:
                raise _TooLarge(f"a power of {right:g} exceeds the limit of {MAX_EXPONENT}")
            return None
        if left in (0.0, 1.0):
            return left
        scale = max(left, 1.0 / left)  # a negative exponent inverts a small base
        digits = right * math.log10(scale)
        if digits > MAX_RESULT_DIGITS:
            raise _TooLarge(f"a number of about 10^{digits:.3g} exceeds {MAX_RESULT_DIGITS} digits")
        return math.inf if digits > 300 else scale**right
    if left is None or right is None:
        return None
    if isinstance(node.op, (ast.Add, ast.Sub)):
        return left + right
    if isinstance(node.op, ast.Mult):
        return left * right
    if isinstance(node.op, ast.Div) and _is_literal(node.right) and right >= 1:
        return left / right
    return math.inf  # numeric but not boundable here (e.g. 1/(1/10^9))


def _call_magnitude(node: ast.Call) -> float | None:
    name = node.func.id if isinstance(node.func, ast.Name) else ""
    args = [_magnitude(arg) for arg in node.args]  # always descend: checks nested powers
    if name in _SYMBOLIC_CONSTRUCTORS:
        return None
    if name in _NUMBER_CONSTRUCTORS:
        if name == "Rational" and len(args) == 2 and None not in args:
            return args[0]  # |p/q| <= |p| for integer q
        return args[0] if args else None
    known = [arg for arg in args if arg is not None]
    if not known or len(known) != len(args):
        return None  # a symbolic argument: sympy keeps the call unevaluated
    largest = max(known)
    if name in _COMBINATORIAL:
        if largest > MAX_COMBINATORIAL_ARGUMENT:
            raise _TooLarge(
                f"{name}({largest:g}) exceeds the limit of {MAX_COMBINATORIAL_ARGUMENT}"
            )
        return math.exp(min(math.lgamma(largest + 1), 700.0))  # n! bounds every listed one
    return largest  # value-preserving or unevaluated (Abs, floor, sqrt, sin, log, exp…)


def _is_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) or (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _NUMBER_CONSTRUCTORS
    )


def _check_growth(machine_text: str) -> None:
    """Raise ``_TooLarge`` if evaluating ``machine_text`` could explode.

    Uses sympy's own tokenizer and transformations to produce the code it would
    run, then bounds it — nothing is evaluated.  Text sympy cannot even
    tokenise is left for ``safe_sympify`` to reject with a parse error.
    """
    from tokenize import TokenError

    from sympy.parsing.sympy_parser import stringify_expr

    namespace, transformations = _parser_context()
    try:
        code = stringify_expr(machine_text.replace("^", "**"), {}, namespace, transformations)
        tree = ast.parse(code, mode="eval")
    except (SyntaxError, TokenError, ValueError, TypeError):
        return
    _magnitude(tree)


def _is_known_word(name: str) -> bool:
    return name in _GREEK or name in _CONSTANTS or name in _function_names()


def _prose_free(sides: list[list[tuple[str, str]]]) -> bool:
    """True when every identifier is maths, not an English word.

    Multi-letter identifiers that are not functions/constants/Greek are allowed
    only as juxtaposed variables already used on their own (``xy`` next to a
    standalone ``x`` and ``y``) — that is how ``the``/``value`` are caught.
    """
    names = [text for tokens in sides for kind, text in tokens if kind == "name"]
    standalone = {name for name in names if _VARIABLE_RE.fullmatch(name)}
    for name in names:
        if _VARIABLE_RE.fullmatch(name) or _is_known_word(name):
            continue
        if not all(letter in standalone for letter in name):
            return False
    return True


# ---------------------------------------------------------------------------
# Parsing (pure text → EquationProblem)
# ---------------------------------------------------------------------------


def parse_equations(text: str) -> EquationProblem | None:
    """Recognise an equation or system in ``text``.

    Returns ``None`` when the text is not an equation problem.  Raises
    ``SolverParseError`` when an explicit instruction (``solve``/``the
    system``) introduces equations that cannot be read — so the caller can tell
    "broken maths" from "not maths".
    """
    if "=" not in text and "＝" not in text:
        return None
    normalised = normalise_notation(text)
    if _INEQUALITY_RE.search(normalised):
        return None

    instruction = _INSTRUCTION_RE.match(normalised)
    explicit = bool(instruction and (instruction.group("verb") or instruction.group("noun")))
    unknowns = _split_vars(instruction.group("pre_vars")) if instruction else ()
    body = normalised[instruction.end() :] if instruction else normalised

    body = _TRAILING_PUNCT_RE.sub("", body)
    trailing = _TRAILING_VARS_RE.search(body)
    if trailing:
        unknowns = unknowns or _split_vars(trailing.group("post_vars"))
        body = body[: trailing.start()]
    braces = _BRACES_RE.match(body.strip())
    if braces:
        body = braces.group(1)

    try:
        equations = _read_equations(body)
        written = {name for eq in equations for side in (eq.lhs, eq.rhs) for name in _names(side)}
        missing = [name for name in unknowns if name not in written]
        if missing:  # checked on the text, so it holds even when terms cancel
            raise _Rejected(f"unknown {', '.join(missing)} does not appear in the equations")
    except _Rejected as rejected:
        # The one decision point: an instruction makes broken maths an error;
        # without one, the text was simply never ours.
        if explicit:
            raise SolverParseError(f"cannot parse equations: {rejected}", expression=body) from None
        return None
    return EquationProblem(equations=equations, unknowns=unknowns, explicit=explicit)


class _Rejected(Exception):
    """``body`` is not a readable set of equations (reason in the message)."""


def _read_equations(body: str) -> tuple[Equation, ...]:
    """Split, tokenise and vet the equations in ``body``; raise ``_Rejected``."""
    pieces = _split_equations(body)
    if not pieces:
        raise _Rejected("no equation after the instruction")
    if len(pieces) > MAX_EQUATIONS:
        raise _Rejected(f"more than {MAX_EQUATIONS} equations")

    sides: list[list[tuple[str, str]]] = []
    for piece in pieces:
        halves = piece.split("=")
        if len(halves) != 2 or not halves[0].strip() or not halves[1].strip():
            raise _Rejected(f"{piece!r} is not a single equation")
        for half in halves:
            tokens = _tokenise(half.strip())
            if tokens is None:
                raise _Rejected(f"{half.strip()!r} is not a mathematical expression")
            sides.append(tokens)
    if not _prose_free(sides):
        raise _Rejected("the text contains words, not just mathematics")

    rebuilt = ["".join(text for _, text in tokens).strip() for tokens in sides]
    for side in rebuilt:
        try:
            _check_growth(_machine_form(side))
        except _TooLarge as too_large:
            raise _Rejected(f"{side!r}: {too_large}") from None
    return tuple(Equation(lhs=rebuilt[i], rhs=rebuilt[i + 1]) for i in range(0, len(rebuilt), 2))


def _names(side: str) -> set[str]:
    """Identifiers written on one side of an equation (already canonical)."""
    return {text for kind, text in _tokenise(side) or [] if kind == "name"}


# ---------------------------------------------------------------------------
# 5. Solving (EquationProblem → WorkedSolution)
# ---------------------------------------------------------------------------


def _new_step(steps: list[SolutionStep], description: str, result: str = "") -> None:
    # Steps are read by students: show x^2, not Python's x**2.  The final
    # answer keeps sympy's spelling, which the eval scorer parses.
    steps.append(
        SolutionStep(n=len(steps) + 1, description=description, result=result.replace("**", "^"))
    )


def _machine_form(side: str) -> str:
    """Display text → text safe for Python's tokenizer under sympy.

    A digit run glued to a name is lexed by Python before sympy sees it:
    ``0x`` starts a hex literal, ``3j`` is the complex number 3i and ``2e`` is
    a malformed exponent.  An explicit ``*`` makes every one a product.
    """
    tokens = _tokenise(side) or []
    out: list[str] = []
    previous = ""
    for kind, text in tokens:
        if kind == "name" and previous == "num":
            out.append("*")
        out.append(text)
        if kind != "space":
            previous = kind
    return "".join(out)


def _sympify(text: str):
    from olivia.tools.science import safe_sympify

    return safe_sympify(text, implicit_multiplication=True)


def _parse_failure_types() -> tuple[type[BaseException], ...]:
    from tokenize import TokenError

    from sympy.core.sympify import SympifyError

    return (
        SympifyError,
        ValueError,
        TypeError,
        ZeroDivisionError,
        ArithmeticError,
        AttributeError,
        SyntaxError,
        TokenError,
    )


def _pick_symbol(expr):
    import sympy

    symbols = sorted(expr.free_symbols, key=lambda s: s.name)
    for symbol in symbols:
        if symbol.name == "x":
            return symbol
    return symbols[0] if symbols else sympy.Symbol("x")


def _choose_unknowns(parsed: EquationProblem, exprs: list) -> list:
    """Requested unknowns, else every symbol — or x/y/z/w when that fits better.

    ``solve x + y = a and x - y = b`` has four symbols but two equations; the
    conventional unknowns are x and y, with a and b as parameters.
    """
    import sympy

    present = set().union(*(expr.free_symbols for expr in exprs))
    if parsed.unknowns:
        chosen = [sympy.Symbol(name) for name in parsed.unknowns]
        missing = [str(s) for s in chosen if s not in present]
        if missing:
            raise SolverParseError(
                f"unknown {', '.join(missing)} does not appear in the equations",
                expression=parsed.describe(),
            )
        return chosen
    ordered = sorted(present, key=lambda s: s.name)
    if len(ordered) > len(exprs):
        conventional = [s for s in ordered if s.name in {"x", "y", "z", "w"}]
        if len(conventional) == len(exprs):
            return conventional
    return ordered


def _check_powers(exprs: list, parsed: EquationProblem) -> None:
    """Refuse computed powers the token check could not see (``x^(8*8*8)``)."""
    import sympy

    for expr in exprs:
        for power in expr.atoms(sympy.Pow):
            if power.exp.is_Number and abs(power.exp) > MAX_EXPONENT:
                raise SolverParseError(
                    f"power {power.exp} exceeds the offline limit of {MAX_EXPONENT}",
                    expression=parsed.describe(),
                )


def _format_roots(roots: list[dict]) -> str:
    import sympy

    return "; ".join(
        ", ".join(f"{symbol} = {sympy.nsimplify(value)}" for symbol, value in root.items())
        for root in roots
    )


def _row_equation(row, unknowns) -> str:
    import sympy

    lhs = sum((row[j] * unknowns[j] for j in range(len(unknowns))), sympy.Integer(0))
    return f"{lhs} = {row[len(unknowns)]}"


def _numeric_linear_system(exprs: list, unknowns: list):
    """``(A, b)`` for a square linear system with numeric coefficients, else None."""
    import sympy
    from sympy.polys.polyerrors import BasePolynomialError

    if len(unknowns) != len(exprs) or len(unknowns) < 2:
        return None
    try:
        matrix, constants = sympy.linear_eq_to_matrix(exprs, unknowns)
    except (ValueError, BasePolynomialError):  # NonlinearError is a ValueError
        return None
    if any(entry.free_symbols for entry in (*matrix, *constants)):
        return None  # symbolic coefficients: elimination would hide case splits
    return matrix, constants


def _elimination_steps(matrix, constants, unknowns: list) -> tuple[list[tuple[str, str]], dict]:
    """Gaussian elimination with back-substitution, as human-readable steps.

    Precondition: ``matrix`` is square and non-singular — the only case where
    row operations alone tell the whole story.
    """
    import sympy

    n = len(unknowns)
    rows = matrix.row_join(constants)
    steps: list[tuple[str, str]] = []
    for col in range(n):
        pivot = next(r for r in range(col, n) if rows[r, col] != 0)
        if pivot != col:
            rows.row_swap(pivot, col)
            steps.append((f"Swap equations {col + 1} and {pivot + 1}", ""))
        for r in range(col + 1, n):
            factor = rows[r, col] / rows[col, col]
            if factor == 0:
                continue
            rows[r, :] = rows[r, :] - factor * rows[col, :]
            steps.append(
                (
                    f"Eliminate {unknowns[col]} from equation {r + 1}: "
                    f"E{r + 1} ← E{r + 1} − ({factor})·E{col + 1}",
                    _row_equation(rows.row(r), unknowns),
                )
            )
    values: dict = {}
    for col in reversed(range(n)):
        known = sum(
            (rows[col, j] * values[unknowns[j]] for j in range(col + 1, n)), sympy.Integer(0)
        )
        values[unknowns[col]] = (rows[col, n] - known) / rows[col, col]
        verb = "Solve the last equation" if col == n - 1 else "Back-substitute"
        steps.append((f"{verb} for {unknowns[col]}", f"{unknowns[col]} = {values[unknowns[col]]}"))
    return steps, values


def _verify(exprs: list, roots: list[dict]) -> bool:
    """Substitute each solution back; True only if every equation holds."""
    import sympy

    # A parametric family (x = 2 - y) must still cancel identically in y.
    return all(sympy.simplify(expr.subs(root)) == 0 for root in roots for expr in exprs)


def _polynomial_steps(expr, var, steps: list[SolutionStep]) -> None:
    """Linear: isolate the unknown.  Quadratic: classify by the discriminant."""
    import sympy
    from sympy.polys.polyerrors import BasePolynomialError

    try:
        poly = sympy.Poly(expr, var)
    except BasePolynomialError:
        return
    if poly.free_symbols - {var}:
        return  # literal coefficients (a*x + b): the general formula is the answer
    if poly.degree() == 1:
        a, b = poly.all_coeffs()
        _new_step(steps, f"Isolate {var}", f"{var} = {-b}/{a}" if a != 1 else f"{var} = {-b}")
    elif poly.degree() == 2:
        a, b, c = poly.all_coeffs()
        disc = sympy.expand(b**2 - 4 * a * c)
        if disc.is_positive:
            kind = "two distinct real roots"
        elif disc.is_zero:
            kind = "one repeated root"
        elif disc.is_negative:
            kind = "two complex conjugate roots"
        else:
            kind = "roots follow from the quadratic formula"
        _new_step(steps, f"Discriminant b² − 4ac = ({b})² − 4·({a})·({c})", f"{disc}: {kind}")


def _solve_single(parsed: EquationProblem, expr, steps: list[SolutionStep]) -> tuple[str, bool]:
    import sympy

    var = _choose_unknowns(parsed, [expr])[0] if parsed.unknowns else _pick_symbol(expr)
    moved = sympy.simplify(expr)
    _new_step(steps, "Move every term to one side", f"{moved} = 0")
    factored = sympy.factor(expr)
    if factored != sympy.expand(expr):
        _new_step(steps, "Factor", f"{factored} = 0")
    _polynomial_steps(expr, var, steps)
    roots = sympy.solve(expr, var)
    answer = ", ".join(f"{var} = {sympy.nsimplify(r)}" for r in roots) or "no solution"
    return answer, _verify([expr], [{var: r} for r in roots])


def _solve_system(
    parsed: EquationProblem, exprs: list, steps: list[SolutionStep]
) -> tuple[str, bool]:
    import sympy

    unknowns = _choose_unknowns(parsed, exprs)
    _new_step(
        steps,
        "Move all terms to one side",
        ", ".join(f"{sympy.simplify(expr)} = 0" for expr in exprs),
    )
    roots = sympy.solve(exprs, unknowns, dict=True)
    linear = _numeric_linear_system(exprs, unknowns)
    if linear is not None:
        matrix, constants = linear
        det = matrix.det()
        if det == 0:
            _new_step(
                steps,
                "The coefficient determinant is 0",
                "no unique solution: the equations are inconsistent or dependent",
            )
        elif len(unknowns) <= MAX_ELIMINATION_UNKNOWNS:
            row_steps, values = _elimination_steps(matrix, constants, unknowns)
            if len(roots) == 1 and all(
                sympy.simplify(roots[0].get(s, s) - v) == 0 for s, v in values.items()
            ):
                for description, result in row_steps:
                    _new_step(steps, description, result)
            else:  # defensive: never show working that disagrees with the answer
                logger.warning("elimination disagrees with sympy for %s", parsed.describe())
    free = [s for s in unknowns if roots and all(s not in root for root in roots)]
    if free:
        names = ", ".join(str(s) for s in free)
        role = "is a free parameter" if len(free) == 1 else "are free parameters"
        _new_step(
            steps, "The equations are dependent", f"infinitely many solutions; {names} {role}"
        )
    answer = _format_roots(roots) or "no solution"
    _new_step(steps, "Solve the system", answer)
    return answer, _verify(exprs, roots)


def solve_parsed(problem: str, parsed: EquationProblem) -> WorkedSolution:
    """Solve an already-parsed equation problem, showing the work."""
    import sympy

    try:
        exprs = [
            _sympify(f"({_machine_form(eq.lhs)})-({_machine_form(eq.rhs)})")
            for eq in parsed.equations
        ]
    except _parse_failure_types() as exc:
        logger.exception("equations: cannot parse %r", parsed.describe())
        raise SolverParseError(
            f"cannot parse equations: {parsed.describe()}", expression=parsed.describe()
        ) from exc
    _check_powers(exprs, parsed)

    steps: list[SolutionStep] = []
    one_equation = len(exprs) == 1
    # "solve x + y = 5 for x and y" asks for two unknowns: the system path
    # reports y as a free parameter instead of silently dropping it.
    single = one_equation and len(parsed.unknowns) <= 1
    _new_step(
        steps, "Restate the equation" if one_equation else "Restate the system", parsed.describe()
    )

    if not any(expr.free_symbols for expr in exprs):
        # Everything cancelled: an identity (0 = 0) or a contradiction (1 = 0).
        holds = all(sympy.simplify(expr) == 0 for expr in exprs)
        answer = "every value is a solution (identity)" if holds else "no solution"
        _new_step(
            steps,
            "Simplify both sides",
            "both sides are always equal" if holds else "the sides can never be equal",
        )
        return WorkedSolution(
            problem=problem,
            subject="math",
            steps=steps,
            final_answer=answer,
            method="symbolic",
            confidence=0.9,
        )

    try:
        if single:
            answer, verified = _solve_single(parsed, exprs[0], steps)
        else:
            answer, verified = _solve_system(parsed, exprs, steps)
    except NotImplementedError as exc:  # sympy: no algorithm for this form
        raise SolverParseError(
            f"no symbolic method for: {parsed.describe()}", expression=parsed.describe()
        ) from exc
    except ValueError as exc:
        # Defence in depth behind _check_growth: Python refuses to print an int
        # of more than 4300 digits.  Never let that escape as a bare ValueError.
        if "integer string conversion" not in str(exc):
            raise
        raise SolverParseError(
            f"result too large to display: {parsed.describe()}", expression=parsed.describe()
        ) from exc

    if answer != "no solution":
        _new_step(
            steps,
            "Check by substituting back into every equation",
            "every equation holds" if verified else "could not be confirmed symbolically",
        )
    return WorkedSolution(
        problem=problem,
        subject="math",
        steps=steps,
        final_answer=answer,
        method="symbolic",
        confidence=0.9 if verified else 0.6,
    )


def solve_equations(problem: str) -> WorkedSolution | None:
    """Solve ``problem`` if it is an equation or system; ``None`` if it is not."""
    parsed = parse_equations(problem.strip())
    if parsed is None:
        return None
    return solve_parsed(problem, parsed)
