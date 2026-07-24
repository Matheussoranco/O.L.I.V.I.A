"""Statistics expert — power analysis computed, the rest reasoned.

Sample-size questions with an extractable effect size are answered exactly by
the symbolic power formula; broader statistical questions go to the LLM with
a quantitative-care addendum.
"""

from __future__ import annotations

import re

from olivia.experts.base import Expert, ExpertAnswer, keyword_score
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import OLIVIA_PERSONA
from olivia.tools.science import required_sample_size

_KEYWORDS = [
    "p-value",
    "p value",
    "effect size",
    "sample size",
    "power",
    "t-test",
    "significance",
    "significant",
    "confidence interval",
    "standard deviation",
    "variance",
    "correlation",
    "regression",
    "anova",
    "hypothesis test",
]
_EFFECT_RE = re.compile(r"(?:\bd\s*=\s*|effect size (?:of\s*)?)([0-9]*\.?[0-9]+)", re.IGNORECASE)
_SAMPLE_INTENT_RE = re.compile(
    r"sample size|how many (?:participants|subjects|samples)", re.IGNORECASE
)

_STATS_ADDENDUM = (
    "\nReport effect sizes and uncertainty, not just p-values; name the test's assumptions."
)


class StatsExpert(Expert):
    name = "stats"
    description = "Statistics: tests, power analysis, effect sizes, study design."

    def score(self, question: str) -> float:
        return keyword_score(question, _KEYWORDS)

    def answer(self, question: str, client: LLMClient | None = None) -> ExpertAnswer:
        if _SAMPLE_INTENT_RE.search(question):
            match = _EFFECT_RE.search(question)
            if match:
                effect = float(match.group(1))
                if effect > 0:
                    n = required_sample_size(effect)
                    return ExpertAnswer(
                        expert=self.name,
                        answer=(
                            f"For a two-sided two-sample test at α = 0.05 and power = 0.80 "
                            f"with effect size d = {effect:g}, you need **n ≈ {n} per group** "
                            f"({2 * n} total; normal approximation)."
                        ),
                        confidence=0.9,
                        details={"effect_size": effect, "n_per_group": n},
                    )

        client = client or get_client()
        if client.available:
            text = client.ask(question, system=OLIVIA_PERSONA + _STATS_ADDENDUM).strip()
            if text:
                return ExpertAnswer(expert=self.name, answer=text, confidence=0.6)
        return ExpertAnswer(
            expert=self.name,
            answer="Cannot answer: no extractable effect size for direct computation "
            "and no LLM backend is configured.",
            confidence=0.0,
        )
