"""Flashcard generation — atomic Q/A pairs from an LLM, cloze cards offline.

The offline path only ever recombines the learner's own material (cloze
deletion over supplied content); it invents nothing, per epistemic honesty.
"""

from __future__ import annotations

import logging
import re

from olivia.core.records import Flashcard
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import OLIVIA_PERSONA
from olivia.llm.structured import ask_json

logger = logging.getLogger(__name__)

_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]")
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]{4,}")


def _cloze_cards(topic: str, content: str, n: int) -> list[Flashcard]:
    """Blank the longest word of each usable sentence — deterministic clozes."""
    cards: list[Flashcard] = []
    for match in _SENTENCE_RE.finditer(content):
        sentence = " ".join(match.group().split())
        if not 30 <= len(sentence) <= 300:
            continue
        words = _WORD_RE.findall(sentence)
        if not words:
            continue
        target = max(words, key=len)
        cards.append(
            Flashcard(
                front=sentence.replace(target, "____", 1),
                back=target,
                topic=topic,
            )
        )
        if len(cards) >= n:
            break
    return cards


def generate_flashcards(
    topic: str,
    content: str = "",
    client: LLMClient | None = None,
    n: int = 10,
) -> list[Flashcard]:
    """Produce up to ``n`` flashcards about ``topic`` (grounded in ``content``)."""
    client = client or get_client()

    if client.available:
        prompt = (
            f"Create up to {n} spaced-repetition flashcards about: {topic}\n"
            + (f"\nGround them in this material:\n{content[:6000]}\n" if content else "")
            + '\nRespond as a JSON list of {"front": "one atomic question", '
            '"back": "concise answer"}. One fact per card; no card should depend on another.'
        )
        payload = ask_json(client, prompt, system=OLIVIA_PERSONA, max_tokens=2500)
        if isinstance(payload, dict):
            payload = payload.get("cards", [])
        if isinstance(payload, list):
            cards = [
                Flashcard(front=str(i["front"]).strip(), back=str(i["back"]).strip(), topic=topic)
                for i in payload
                if isinstance(i, dict)
                and str(i.get("front", "")).strip()
                and str(i.get("back", "")).strip()
            ]
            if cards:
                return cards[:n]

    if content:
        return _cloze_cards(topic, content, n)
    logger.warning("generate_flashcards: no LLM and no content — nothing to build from")
    return []
