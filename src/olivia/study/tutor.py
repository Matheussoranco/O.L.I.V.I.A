"""Socratic tutor — a stateful conversation, one focused question at a time.

The tutor never lectures unprompted (see TUTOR_SYSTEM): it diagnoses from the
learner's own explanations, Feynman-style, offers incremental hints on demand,
surfaces misconceptions through targeted questions, tracks session state across
turns, and closes gracefully with a structured summary.  Offline it degrades to
an honest notice rather than canned pseudo-tutoring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import TUTOR_SYSTEM
from olivia.llm.structured import ask_json

logger = logging.getLogger(__name__)

_OFFLINE_NOTICE = (
    "No LLM backend is configured, so live tutoring is unavailable. "
    "Set OLIVIA_LLM__PROVIDER (anthropic | ollama) to enable it. Meanwhile: "
    "write down your own explanation of the topic, then check it against your "
    "sources — the gaps you find are your study plan."
)

_OFFLINE_HINT_NOTICE = (
    "No LLM backend is configured, so live hints are unavailable. "
    "Try testing your intuition on a single concrete edge case of the topic "
    "and check each assumption against your notes."
)

_SOCRATIC_PROTOCOL = """
Interactive Socratic rules:
- Ask one focused guiding question at a time; never dump a lecture.
- Acknowledge what the learner got right, then pinpoint any misconception with a
  concise correction and a probing follow-up question.
- When the learner asks for a hint, give one small nudge that unlocks the next
  step without spoiling the full answer.
"""

EXIT_COMMANDS: frozenset[str] = frozenset({"/exit", "/quit", "exit", "quit", ":q"})
SUMMARY_COMMANDS: frozenset[str] = frozenset({"/summary", "/status"})
HELP_COMMANDS: frozenset[str] = frozenset({"/help", "?"})

TUTOR_HELP_TEXT = (
    "Commands:\n"
    "- `/hint [focus]` — ask for a small Socratic nudge without spoiling the answer\n"
    "- `/summary` — view a progress summary without ending the session\n"
    "- `/help` — show these commands\n"
    "- `/exit` (or `quit`, Ctrl-C) — end gracefully with a session summary"
)


@dataclass
class TutorState:
    """Mutable progress metadata tracked across turns of a tutoring session."""

    topic: str
    turns: int = 0
    hints_used: int = 0
    opening_question: str = ""
    ended: bool = False


@dataclass
class TutorSummary:
    """Structured summary emitted on `/summary` or graceful session exit."""

    topic: str
    turns: int
    hints_used: int
    mode: str
    opening_question: str = ""
    covered: list[str] = field(default_factory=list)
    misconceptions_addressed: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)


def _clean_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                out.append(stripped)
    return out


class TutorSession:
    """One Socratic tutoring conversation about a fixed topic."""

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
        self.state = TutorState(topic=topic)
        self._system = TUTOR_SYSTEM + _SOCRATIC_PROTOCOL + f"\nCurrent topic: {topic}"

    def _system_with_state(self) -> str:
        """Build the system prompt enriched with current session state."""
        parts = [
            self._system,
            f"Session state: turn={self.state.turns}, hints_used={self.state.hints_used}",
        ]
        if self.state.opening_question:
            parts.append(f"Opening question posed: {self.state.opening_question}")
        return "\n".join(parts)

    def _history_window(self) -> list[dict[str, str]]:
        window = self.messages[-self.max_history :]
        if window and window[0]["role"] != "user":
            window = window[1:]
        return window

    def suggest_question(self) -> str:
        """One Socratic opener for the topic."""
        question = ""
        if self.client.available:
            question = self.client.ask(
                f"Give exactly one short Socratic opening question to probe a learner's "
                f"current understanding of {self.topic}. Only the question.",
                system=self._system,
            ).strip()
        if not question:
            question = (
                f"In your own words, what problem does {self.topic} solve, "
                "and what would break without it?"
            )
        self.state.opening_question = question
        return question

    def respond(self, user_message: str) -> str:
        """Add the learner's message and return the tutor's Socratic reply."""
        self.state.turns += 1
        self.messages.append({"role": "user", "content": user_message})
        if not self.client.available:
            reply = _OFFLINE_NOTICE
        else:
            response = self.client.complete(
                self._history_window(),
                system=self._system_with_state(),
            )
            reply = response.text.strip() or (
                f"(tutor unavailable: {response.error or 'empty response'})"
            )
        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def request_hint(self, focus: str = "") -> str:
        """Offer one small Socratic hint without spoiling the full answer."""
        self.state.hints_used += 1
        focus_clean = focus.strip()
        prompt = (
            f"The learner requested a hint about: {focus_clean}. "
            if focus_clean
            else "The learner requested a hint on the current question. "
        ) + (
            "Give one concise Socratic hint (1-2 sentences) that guides them "
            "toward the next step without giving away the full answer."
        )
        self.messages.append({"role": "user", "content": f"[hint request] {focus_clean}".strip()})
        if not self.client.available:
            reply = _OFFLINE_HINT_NOTICE
        else:
            window = self._history_window()
            # Replace the synthetic marker in the last message with the explicit hint instruction
            # while keeping the stored transcript concise.
            call_messages = [*window[:-1], {"role": "user", "content": prompt}]
            response = self.client.complete(call_messages, system=self._system_with_state())
            reply = response.text.strip() or (
                f"(hint unavailable: {response.error or 'empty response'})"
            )
        self.messages.append({"role": "assistant", "content": reply})
        return reply

    def summarize(self) -> TutorSummary:
        """Produce a structured summary of progress, misconceptions, and next steps."""
        if self.client.available and self.messages:
            transcript = "\n".join(
                f"{m['role'].upper()}: {m['content']}" for m in self.messages[-self.max_history :]
            )
            prompt = (
                f"Summarise this Socratic tutoring session on '{self.topic}'.\n"
                "Return a JSON object with keys:\n"
                '- "covered": list of 1-4 concise concepts explored\n'
                '- "misconceptions_addressed": list of misconceptions clarified (empty if none)\n'
                '- "next_steps": list of 1-3 concrete follow-up study actions\n'
                "Stay strictly grounded in the transcript; do not invent topics not discussed.\n\n"
                f"Transcript:\n{transcript}"
            )
            payload = ask_json(self.client, prompt, system=self._system, max_tokens=600)
            if isinstance(payload, dict):
                covered = _clean_str_list(payload.get("covered"))
                misconceptions = _clean_str_list(payload.get("misconceptions_addressed"))
                next_steps = _clean_str_list(payload.get("next_steps"))
                if covered or misconceptions or next_steps:
                    return TutorSummary(
                        topic=self.topic,
                        turns=self.state.turns,
                        hints_used=self.state.hints_used,
                        mode="llm",
                        opening_question=self.state.opening_question,
                        covered=covered or [self.topic],
                        misconceptions_addressed=misconceptions,
                        next_steps=next_steps
                        or [f"Reinforce {self.topic} with active recall flashcards or a quiz."],
                    )

        # Deterministic honest fallback (offline, zero-turn exit, or malformed LLM JSON).
        fallback_mode = "offline" if not self.client.available else "deterministic_fallback"
        user_turns = [
            m["content"].strip()
            for m in self.messages
            if m["role"] == "user" and not m["content"].startswith("[hint request]")
        ]
        covered = [
            f"Explored '{self.topic}' across {self.state.turns} learner turn(s)."
            if self.state.turns
            else f"Opened session on '{self.topic}' (no learner responses recorded yet)."
        ]
        if user_turns:
            preview = user_turns[-1]
            if len(preview) > 90:
                preview = preview[:87] + "..."
            covered.append(f'Latest learner response: "{preview}"')

        next_steps = (
            [
                (
                    "Configure an LLM backend (OLIVIA_LLM__PROVIDER=anthropic|ollama) "
                    "for live Socratic feedback."
                ),
                (
                    f"Write a short Feynman-style explanation of {self.topic} "
                    "and verify against primary sources."
                ),
            ]
            if not self.client.available
            else [
                f'Generate spaced-repetition cards: olivia study cards "{self.topic}"',
                f'Test recall with a short quiz: olivia study quiz "{self.topic}"',
            ]
        )
        return TutorSummary(
            topic=self.topic,
            turns=self.state.turns,
            hints_used=self.state.hints_used,
            mode=fallback_mode,
            opening_question=self.state.opening_question,
            covered=covered,
            misconceptions_addressed=[],
            next_steps=next_steps,
        )

    def handle_input(self, raw_input: str) -> tuple[str, bool]:
        """Process one interactive input line.

        Returns ``(output_markdown, should_exit)``.
        """
        text = raw_input.strip()
        if not text:
            return ("", False)

        lowered = text.lower()
        if lowered in EXIT_COMMANDS:
            self.state.ended = True
            return (summary_to_markdown(self.summarize()), True)

        if lowered in SUMMARY_COMMANDS:
            return (summary_to_markdown(self.summarize()), False)

        if lowered in HELP_COMMANDS:
            return (TUTOR_HELP_TEXT, False)

        if lowered == "hint" or lowered == "/hint" or lowered.startswith("/hint "):
            focus = text[5:].strip() if lowered.startswith("/hint") else ""
            return (self.request_hint(focus), False)

        return (self.respond(text), False)


def summary_to_markdown(summary: TutorSummary) -> str:
    """Render a :class:`TutorSummary` as clean Markdown."""
    lines = [
        f"## Tutor Session Summary: {summary.topic}",
        "",
        f"- **Turns:** {summary.turns}",
        f"- **Hints used:** {summary.hints_used}",
        f"- **Mode:** {summary.mode}",
    ]
    if summary.opening_question:
        lines.append(f"- **Opening question:** {summary.opening_question}")

    lines.extend(["", "### Concepts Explored"])
    for item in summary.covered or [summary.topic]:
        lines.append(f"- {item}")

    lines.extend(["", "### Misconceptions Addressed"])
    if summary.misconceptions_addressed:
        for item in summary.misconceptions_addressed:
            lines.append(f"- {item}")
    else:
        lines.append("- None recorded in this session.")

    lines.extend(["", "### Suggested Next Steps"])
    for item in summary.next_steps or [f"Review {summary.topic} with active recall."]:
        lines.append(f"- {item}")

    return "\n".join(lines) + "\n"
