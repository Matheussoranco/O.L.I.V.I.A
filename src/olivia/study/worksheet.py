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
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import SOLVER_SYSTEM
from olivia.llm.structured import ask_json
from olivia.study.solver import SolutionStep, solution_to_markdown, solve_problem

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
        problem = generator(rng, difficulty)
        solutions.append(solve_problem(problem, subject="math", client=None))
    return solutions


def _llm_worksheet(topic: str, n: int, difficulty: str, client: LLMClient) -> list[WorkedSolution]:
    prompt = (
        f"Create a {difficulty} practice worksheet of {n} problems on: {topic}\n\n"
        'Respond as JSON: {"problems": [{"problem": str, '
        '"steps": [{"description": str, "result": str}], "answer": str}]}. '
        "Each problem must be self-contained with a complete worked solution."
    )
    payload = ask_json(client, prompt, system=SOLVER_SYSTEM, max_tokens=3500)
    if not isinstance(payload, dict) or not isinstance(payload.get("problems"), list):
        return []
    solutions: list[WorkedSolution] = []
    for entry in payload["problems"]:
        if not isinstance(entry, dict) or not str(entry.get("problem", "")).strip():
            continue
        raw_steps = entry.get("steps") if isinstance(entry.get("steps"), list) else []
        steps = [
            SolutionStep(
                n=i + 1,
                description=str(s.get("description", "")).strip(),
                result=str(s.get("result", "")).strip(),
            )
            for i, s in enumerate(raw_steps)
            if isinstance(s, dict) and str(s.get("description", "")).strip()
        ]
        solutions.append(
            WorkedSolution(
                problem=str(entry["problem"]).strip(),
                subject="general",
                steps=steps,
                final_answer=str(entry.get("answer", "")).strip(),
                method="llm",
                confidence=0.7,
            )
        )
    return solutions[:n]


def generate_worksheet(
    topic: str,
    n: int = 5,
    difficulty: str = "medium",
    client: LLMClient | None = None,
    seed: int | None = None,
) -> list[WorkedSolution]:
    """Produce up to ``n`` practice problems on ``topic``, each fully solved."""
    client = client or get_client()
    if client.available:
        solutions = _llm_worksheet(topic, n, difficulty, client)
        if solutions:
            return solutions
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
