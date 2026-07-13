"""Code expert — runs fenced Python when execution is asked for, else reasons.

Execution goes through the same isolated ``python_exec`` sandbox the research
cycle uses; observed output always beats predicted output.
"""

from __future__ import annotations

import re

from olivia.experts.base import Expert, ExpertAnswer, keyword_score
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import OLIVIA_PERSONA
from olivia.tools.science import python_exec

_KEYWORDS = [
    "code", "function", "python", "bug", "error", "traceback", "implement",
    "script", "algorithm", "refactor", "debug", "exception",
]
_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)
_RUN_INTENT_RE = re.compile(r"\b(run|execute|output|result|print)\b", re.IGNORECASE)

_CODE_ADDENDUM = "\nAnswer with working, idiomatic code and a one-line explanation."


class CodeExpert(Expert):
    name = "code"
    description = "Programming: write, explain, debug, and execute Python."

    def score(self, question: str) -> float:
        score = keyword_score(question, _KEYWORDS)
        if "```" in question:
            score = min(score + 0.3, 0.95)
        return score

    def answer(self, question: str, client: LLMClient | None = None) -> ExpertAnswer:
        fence = _FENCE_RE.search(question)
        if fence and _RUN_INTENT_RE.search(question):
            output = python_exec(fence.group(1))
            if output.get("ok"):
                return ExpertAnswer(
                    expert=self.name,
                    answer=f"Executed. Output:\n```\n{output['stdout'].strip()}\n```",
                    confidence=0.85,
                    details={"engine": "python_exec"},
                )
            return ExpertAnswer(
                expert=self.name,
                answer=f"Execution failed:\n```\n{output.get('stderr', '').strip()}\n```",
                confidence=0.7,
                details={"engine": "python_exec", "ok": False},
            )

        client = client or get_client()
        if client.available:
            text = client.ask(question, system=OLIVIA_PERSONA + _CODE_ADDENDUM).strip()
            if text:
                return ExpertAnswer(expert=self.name, answer=text, confidence=0.6)
        return ExpertAnswer(
            expert=self.name,
            answer="Cannot answer: no runnable code block found and no LLM backend "
            "is configured.",
            confidence=0.0,
        )
