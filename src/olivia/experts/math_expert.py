"""Math expert — symbolic first (sympy), LLM second, honesty last.

A recognisable "solve/differentiate/integrate/simplify <expression>" question
is answered by the computer algebra system with high confidence; anything
mathier than the heuristics can parse defers to the LLM at lower confidence.
"""

from __future__ import annotations

import re

from olivia.experts.base import Expert, ExpertAnswer, keyword_score
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import OLIVIA_PERSONA
from olivia.tools.science import symbolic_math

_KEYWORDS = [
    "solve", "equation", "integrate", "integral", "derivative", "differentiate",
    "simplify", "factor", "expand", "polynomial", "limit", "algebra", "calculus",
]
_EXPR_RE = re.compile(r"[0-9a-z)\s]\s*[-+*/^]\s*[0-9a-z(]|\*\*|sqrt|sin\(|cos\(|exp\(|log\(")

_SOLVE_RE = re.compile(r"\bsolve\b\s*:?\s*(.+?)\s*=\s*(.+?)(?:\s+for\b.*)?[.?]?$", re.IGNORECASE)

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (_SOLVE_RE, "solve"),
    (re.compile(r"\b(?:differentiate|derivative of)\b\s*:?\s*(.+?)[.?]?$", re.IGNORECASE), "diff"),
    (re.compile(r"\bintegra(?:te|l of)\b\s*:?\s*(.+?)[.?]?$", re.IGNORECASE), "integrate"),
    (re.compile(r"\bsimplify\b\s*:?\s*(.+?)[.?]?$", re.IGNORECASE), "simplify"),
    (re.compile(r"\bfactor\b\s*:?\s*(.+?)[.?]?$", re.IGNORECASE), "factor"),
    (re.compile(r"\bexpand\b\s*:?\s*(.+?)[.?]?$", re.IGNORECASE), "expand"),
]

_MATH_ADDENDUM = "\nAnswer with exact symbolic mathematics; show the key steps briefly."


class MathExpert(Expert):
    name = "math"
    description = "Symbolic mathematics: solve, differentiate, integrate, simplify."

    def score(self, question: str) -> float:
        score = keyword_score(question, _KEYWORDS)
        if _EXPR_RE.search(question.lower()):
            score = min(score + 0.25, 0.95)
        return score

    def _try_symbolic(self, question: str) -> tuple[str, str] | None:
        """Return (operation, result) when a CAS pattern matches and computes."""
        for pattern, operation in _PATTERNS:
            match = pattern.search(question.strip())
            if not match:
                continue
            if operation == "solve":
                expression = f"({match.group(1).strip()}) - ({match.group(2).strip()})"
            else:
                expression = match.group(1).strip()
            result = symbolic_math(expression, operation)
            if not result.startswith("error:"):
                return operation, result
        return None

    def answer(self, question: str, client: LLMClient | None = None) -> ExpertAnswer:
        symbolic = self._try_symbolic(question)
        if symbolic:
            operation, result = symbolic
            return ExpertAnswer(
                expert=self.name,
                answer=f"{operation}: **{result}** (computed symbolically)",
                confidence=0.9,
                details={"engine": "sympy", "operation": operation},
            )

        client = client or get_client()
        if client.available:
            text = client.ask(question, system=OLIVIA_PERSONA + _MATH_ADDENDUM).strip()
            if text:
                return ExpertAnswer(expert=self.name, answer=text, confidence=0.6)
        return ExpertAnswer(
            expert=self.name,
            answer="Cannot compute: the expression was not parseable symbolically "
            "and no LLM backend is configured.",
            confidence=0.0,
        )
