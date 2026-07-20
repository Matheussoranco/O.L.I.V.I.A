"""Science expert — STEM problem solving via the deterministic solver first.

Chemistry (molar mass, balancing), physics constants, and unit conversion are
answered exactly by O.L.I.V.I.A.'s symbolic tools, with the LLM as a fallback
for open-ended science questions and honesty as the last resort offline.
"""

from __future__ import annotations

import re

from olivia.experts.base import Expert, ExpertAnswer, keyword_score
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import OLIVIA_PERSONA

_KEYWORDS = [
    "molar mass", "molecular weight", "molecular mass", "stoichiometry",
    "balance", "chemical", "chemistry", "compound", "reaction", "mole",
    "molarity", "periodic", "physics", "constant", "speed of light", "planck",
    "avogadro", "boltzmann", "gravitational constant", "convert",
    "dimensional analysis", "unit conversion", "atomic mass", "atomic weight",
]
_FORMULA_HINT = re.compile(
    r"\b[A-Z][a-z]?\d|->|→|\bmol\b|\d+\s*(?:kg|km|mph|mol|mL|nm|°[CF])\b"
)
_SCIENCE_ADDENDUM = (
    "\nAnswer as a scientist: state assumptions, carry units through, and give "
    "the numeric result with its unit."
)


class ScienceExpert(Expert):
    name = "science"
    description = (
        "STEM problem solving: chemistry (molar mass, balancing), physics "
        "constants, unit conversion, step-by-step."
    )

    def score(self, question: str) -> float:
        score = keyword_score(question, _KEYWORDS)
        if _FORMULA_HINT.search(question):
            score = min(score + 0.2, 0.95)
        return score

    def answer(self, question: str, client: LLMClient | None = None) -> ExpertAnswer:
        from olivia.study.solver import solution_to_markdown, solve_problem

        client = client or get_client()
        solution = solve_problem(question, client=client)
        if solution.method in ("symbolic", "chemistry", "physics", "units"):
            return ExpertAnswer(
                expert=self.name,
                answer=solution_to_markdown(solution),
                confidence=solution.confidence,
                details={"method": solution.method, "answer": solution.final_answer},
            )
        if solution.method == "llm":
            return ExpertAnswer(
                expert=self.name,
                answer=solution_to_markdown(solution),
                confidence=solution.confidence,
                details={"method": "llm"},
            )
        if client.available:
            text = client.ask(question, system=OLIVIA_PERSONA + _SCIENCE_ADDENDUM).strip()
            if text:
                return ExpertAnswer(expert=self.name, answer=text, confidence=0.6)
        return ExpertAnswer(
            expert=self.name,
            answer="Cannot solve offline: no matching symbolic method "
            "(chemistry, physics, or unit conversion) and no LLM backend.",
            confidence=0.0,
        )
