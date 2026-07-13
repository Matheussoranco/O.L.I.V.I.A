"""General expert — the LLM catch-all with a constant routing floor.

Its 0.2 floor means it only wins routing when no specialist scores higher,
and it is the honest last resort offline (confidence 0, clear explanation).
"""

from __future__ import annotations

from olivia.experts.base import Expert, ExpertAnswer
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import OLIVIA_PERSONA

_FLOOR = 0.2


class GeneralExpert(Expert):
    name = "general"
    description = "General questions answered by the configured LLM."

    def score(self, question: str) -> float:
        return _FLOOR

    def answer(self, question: str, client: LLMClient | None = None) -> ExpertAnswer:
        client = client or get_client()
        if client.available:
            text = client.ask(question, system=OLIVIA_PERSONA).strip()
            if text:
                return ExpertAnswer(expert=self.name, answer=text, confidence=0.5)
        return ExpertAnswer(
            expert=self.name,
            answer="No LLM backend is configured, so this question cannot be answered. "
            "Set OLIVIA_LLM__PROVIDER=anthropic (with ANTHROPIC_API_KEY) or "
            "OLIVIA_LLM__PROVIDER=ollama for a local model.",
            confidence=0.0,
        )
