"""Practice worksheets — problem sets with worked solutions (GPAI exam-prep).

Online, the LLM writes a themed problem set and O.L.I.V.I.A. solves each item
through the deterministic solver so the answer key is trustworthy.  Offline, a
seeded generator emits randomised maths problems (linear, quadratic,
derivative, arithmetic) whose solutions come from sympy — genuinely useful with
no backend.  Topics outside those generators degrade to an empty set, honestly.
"""

from __future__ import annotations

import logging
import random
import re

from olivia.core.records import WorkedSolution
from olivia.llm.client import LLMClient, NullClient, get_client
from olivia.llm.prompts import SOLVER_SYSTEM
from olivia.llm.structured import ask_json
from olivia.study.solver import solution_to_markdown, solve_problem

logger = logging.getLogger(__name__)

_DIFFICULTY_RANGE = {"easy": (1, 9), "medium": (2, 12), "hard": (5, 25)}


def _span(difficulty: str) -> tuple[int, int]:
    return _DIFFICULTY_RANGE.get(difficulty, _DIFFICULTY_RANGE["medium"])


def _gen_linear(rng: random.Random, difficulty: str) -> str:
    _, hi = _span(difficulty)
    a = rng.randint(2, hi)
    x = rng.randint(-hi, hi)
    b = rng.randint(-hi, hi)
    c = a * x + b
    sign = "+" if b >= 0 else "-"
    return f"solve {a}*x {sign} {abs(b)} = {c} for x"


def _gen_quadratic(rng: random.Random, difficulty: str) -> str:
    import sympy

    _, hi = _span(difficulty)
    r1, r2 = rng.randint(-hi, hi), rng.randint(-hi, hi)
    x = sympy.Symbol("x")
    poly = sympy.expand((x - r1) * (x - r2))
    return f"solve {poly} = 0 for x"


def _gen_derivative(rng: random.Random, difficulty: str) -> str:
    _, hi = _span(difficulty)
    a, b = rng.randint(2, hi), rng.randint(1, hi)
    power = rng.randint(2, 4)
    return f"differentiate {a}*x**{power} + {b}*x"


def _gen_arithmetic(rng: random.Random, difficulty: str) -> str:
    lo, hi = _span(difficulty)
    a, b, c = (rng.randint(lo, hi) for _ in range(3))
    return f"what is {a} * {b} + {c}"


_GENERATORS = {
    ("deriv", "calculus", "differentiat"): _gen_derivative,
    ("quadratic",): _gen_quadratic,
    ("linear", "algebra", "equation"): _gen_linear,
    ("arithmetic", "multiplication", "addition", "times table"): _gen_arithmetic,
}


def _offline_worksheet(
    topic: str, n: int, difficulty: str, seed: int | None
) -> list[WorkedSolution]:
    low = topic.lower()
    generator = next(
        (gen for keys, gen in _GENERATORS.items() if any(k in low for k in keys)),
        None,
    )
    if generator is None:
        logger.warning("worksheet: no offline generator for topic %r", topic)
        return []
    rng = random.Random(seed)
    solutions: list[WorkedSolution] = []
    for _ in range(n):
        try:
            problem = generator(rng, difficulty)
        except ImportError:
            logger.warning("worksheet: topic %r needs an optional dependency", topic)
            return []
        solutions.append(solve_problem(problem, subject="math", client=NullClient()))
    return [solution for solution in solutions if solution.method != "none"]


_CONTENT_PROBLEM_RE = re.compile(
    r"^(?:(?:problem|exercise|question)\s*\d*\s*[:.)-]\s*)?"
    r"(?P<problem>(?:solve|differentiate|integrate|factor|simplify|expand|convert|"
    r"molar\s+mass|balance|what\s+is)\b.+)$",
    re.IGNORECASE,
)
_EQUATION_LINE_RE = re.compile(r"^[0-9a-zA-Z\s+\-*/^().]+=\s*[0-9a-zA-Z\s+\-*/^().]+$")


def _extract_content_problems(content: str, limit: int) -> list[WorkedSolution]:
    """Extract explicitly solvable STEM problems from supplied source text."""
    if not content.strip() or limit <= 0:
        return []
    solutions: list[WorkedSolution] = []
    seen: set[str] = set()
    for raw_segment in re.split(r"[\n;]+|(?<=[.!?])\s+", content):
        line = " ".join(raw_segment.split()).strip(" .")
        if not 4 <= len(line) <= 180:
            continue
        match = _CONTENT_PROBLEM_RE.match(line)
        if match:
            candidate = match.group("problem").strip()
        elif _EQUATION_LINE_RE.match(line) and re.search(r"[a-zA-Z]", line):
            candidate = f"solve {line}"
        else:
            continue
        key = candidate.casefold()
        if key in seen:
            continue
        sol = solve_problem(candidate, client=NullClient())
        if sol.method != "none" and sol.final_answer:
            seen.add(key)
            solutions.append(sol)
            if len(solutions) >= limit:
                break
    return solutions


_GROUNDING_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "answer",
        "because",
        "before",
        "between",
        "calculate",
        "compute",
        "determine",
        "does",
        "during",
        "each",
        "evaluate",
        "exercise",
        "find",
        "following",
        "from",
        "given",
        "have",
        "into",
        "more",
        "must",
        "notes",
        "only",
        "over",
        "problem",
        "question",
        "result",
        "show",
        "solve",
        "solving",
        "step",
        "such",
        "than",
        "that",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "under",
        "using",
        "value",
        "what",
        "when",
        "where",
        "which",
        "while",
        "will",
        "with",
        "within",
        "without",
        "your",
    }
)
_MATH_DOMAIN_RULES: tuple[tuple[tuple[str, ...], re.Pattern[str]], ...] = (
    (
        ("linear", "first-degree", "one variable", "algebra"),
        re.compile(r"\bsolve\b[^=]*=[^=]+$", re.IGNORECASE),
    ),
    (
        ("quadratic", "parabola", "discriminant", "roots"),
        re.compile(r"(?:\*\*\s*2|\^\s*2|quadratic)", re.IGNORECASE),
    ),
    (
        ("derivative", "differentiat", "calculus"),
        re.compile(r"\b(?:differentiate|derivative)\b", re.IGNORECASE),
    ),
    (
        ("integral", "integrat", "antiderivative", "calculus"),
        re.compile(r"\b(?:integrate|integral)\b", re.IGNORECASE),
    ),
    (
        ("factor", "polynomial", "expand"),
        re.compile(r"\b(?:factor|expand|simplify)\b", re.IGNORECASE),
    ),
)


def _content_tokens(text: str) -> tuple[set[str], set[str]]:
    words = {
        w.casefold()
        for w in re.findall(r"[A-Za-z]{4,}", text)
        if w.casefold() not in _GROUNDING_STOPWORDS
    }
    stems = {w[:5] if len(w) >= 6 else w for w in words}
    literals = {
        tok.casefold()
        for tok in re.findall(r"\b\d+(?:\.\d+)?\b|\b[A-Z][a-z]?(?:\d+[A-Z]?[a-z]?\d*)+\b", text)
    }
    return stems, literals


def _is_grounded_in_content(problem: str, content: str) -> bool:
    """Return True if ``problem`` shares domain/numeric terms or math topic with ``content``."""
    content_stems, content_literals = _content_tokens(content)
    prob_stems, prob_literals = _content_tokens(problem)
    if (prob_stems & content_stems) or (prob_literals & content_literals):
        return True
    low_content = content.casefold()
    for cues, prob_re in _MATH_DOMAIN_RULES:
        if any(cue in low_content for cue in cues) and prob_re.search(problem):
            # Guard quadratic expressions from matching plain linear-only notes.
            if cues[0] == "linear" and re.search(r"\*\*\s*[2-9]|\^\s*[2-9]", problem):
                continue
            return True
    return False


def _llm_worksheet(
    topic: str,
    n: int,
    difficulty: str,
    client: LLMClient,
    content: str = "",
) -> list[WorkedSolution]:
    prompt = (
        f"Create a {difficulty} practice worksheet of {n} problems on: {topic}\n"
        + (f"\nGround them in this material:\n{content[:6000]}\n" if content else "")
        + '\nRespond as JSON: {"problems": [str]}. Each problem must be self-contained '
        "and solvable without the original source material."
    )
    payload = ask_json(client, prompt, system=SOLVER_SYSTEM, max_tokens=1500)
    if not isinstance(payload, dict) or not isinstance(payload.get("problems"), list):
        return []
    problems = [str(item).strip() for item in payload["problems"] if str(item).strip()]
    if content.strip():
        grounded = [p for p in problems if _is_grounded_in_content(p, content)]
        dropped = len(problems) - len(grounded)
        if dropped:
            logger.warning(
                "worksheet: dropped %d ungrounded LLM problem(s) for topic %r",
                dropped,
                topic,
            )
        problems = grounded
    solutions = [solve_problem(problem, client=NullClient()) for problem in problems[:n]]
    return [solution for solution in solutions if solution.method != "none"]


def generate_worksheet(
    topic: str,
    n: int = 5,
    difficulty: str = "medium",
    client: LLMClient | None = None,
    seed: int | None = None,
    content: str = "",
) -> list[WorkedSolution]:
    """Produce up to ``n`` practice problems on ``topic``, each fully solved."""
    n = min(max(int(n), 1), 100)
    client = client or get_client()
    if client.available:
        solutions = _llm_worksheet(topic, n, difficulty, client, content=content)
        if solutions:
            return solutions
    if content.strip():
        extracted = _extract_content_problems(content, n)
        if not extracted:
            logger.warning(
                "worksheet: insufficient solvable content in supplied source for topic %r",
                topic,
            )
            return []
        return extracted[:n]
    return _offline_worksheet(topic, n, difficulty, seed)


def worksheet_to_markdown(
    solutions: list[WorkedSolution],
    topic: str = "",
    include_solutions: bool = True,
) -> str:
    """Render a worksheet as markdown — problems, then an optional answer key."""
    heading = f"# Worksheet: {topic}" if topic else "# Practice worksheet"
    lines = [heading, ""]
    for i, solution in enumerate(solutions, 1):
        lines.append(f"**{i}.** {solution.problem}")
    if include_solutions:
        lines += ["", "## Answer key", ""]
        for i, solution in enumerate(solutions, 1):
            body = re.sub(r"^\*\*Problem:\*\*.*\n\n", "", solution_to_markdown(solution))
            lines += [f"### {i}. {solution.problem}", body, ""]
    return "\n".join(lines).rstrip() + "\n"
