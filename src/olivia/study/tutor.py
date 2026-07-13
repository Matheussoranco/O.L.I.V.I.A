"""Socratic tutor — a stateful conversation, one focused question at a time.

The tutor never lectures unprompted (see TUTOR_SYSTEM): it diagnoses from the
learner's own explanations, Feynman-style.  Offline it degrades to an honest
notice rather than canned pseudo-tutoring.
"""

from __future__ import annotations

import logging

from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import TUTOR_SYSTEM

logger = logging.getLogger(__name__)

_OFFLINE_NOTICE = (
    "No LLM backend is configured, so live tutoring is unavailable. "
    "Set OLIVIA_LLM__PROVIDER (anthropic | ollama) to enable it. Meanwhile: "
    "write down your own explanation of the topic, then check it against your "
    "sources — the gaps you find are your study plan."
)


class TutorSession:
    """One tutoring conversation about a fixed topic."""

    def __init__(
        self,
        topic: str,
        client: LLMClient | None = None,
        max_history: int = 40,
    ) -> None:
        self.topic = topic
        self.client = client or get_client()
        self.max_history = max_history
        self.messages: list[dict[str, str]] = []
        self._system = TUTOR_SYSTEM + f"\nCurrent topic: {topic}"

    def respond(self, user_message: str) -> str:
        """Add the learner's message and return the tutor's reply."""
        self.messages.append({"role": "user", "content": user_message})
        if not self.client.available:
            reply = _OFFLINE_NOTICE
        else:
            window = self.messages[-self.max_history :]
            response = self.client.complete(window, system=self._system)
            reply = response.text.strip() or (
                f"(tutor unavailable: {response.error or 'empty response'})"
            )
        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def suggest_question(self) -> str:
        """One Socratic opener for the topic."""
        if self.client.available:
            text = self.client.ask(
                f"Give exactly one short Socratic opening question to probe a learner's "
                f"current understanding of {self.topic}. Only the question.",
                system=self._system,
            ).strip()
            if text:
                return text
        return (
            f"In your own words, what problem does {self.topic} solve, "
            "and what would break without it?"
        )
