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

_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]|[^.!?]+$")
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]{4,}")
_STOPWORDS = {
    "about",
    "after",
    "between",
    "could",
    "does",
    "from",
    "have",
    "into",
    "that",
    "their",
    "these",
    "this",
    "through",
    "using",
    "which",
    "with",
}


def _occurs_once(word: str, sentence: str) -> bool:
    return len(re.findall(rf"\b{re.escape(word)}\b", sentence, re.IGNORECASE)) == 1


def _cloze_cards(topic: str, content: str, n: int) -> list[Flashcard]:
    """Blank unique content words of usable sentences — deterministic grounded clozes."""
    sentence_candidates: list[tuple[str, list[str]]] = []
    for match in _SENTENCE_RE.finditer(content):
        sentence = " ".join(match.group().split())
        if not 30 <= len(sentence) <= 300:
            continue
        words = [word for word in _WORD_RE.findall(sentence) if word.casefold() not in _STOPWORDS]
        candidates = sorted(
            (word for word in words if _occurs_once(word, sentence)),
            key=len,
            reverse=True,
        )
        if candidates:
            sentence_candidates.append((sentence, candidates))

    cards: list[Flashcard] = []
    seen_fronts: set[str] = set()

    # Pass 1: one highest-salience (longest) unique non-stopword per sentence.
    # Subsequent passes fill remaining slots when a concise source has < n sentences.
    pass_idx = 0
    while len(cards) < n:
        progressed = False
        for sentence, candidates in sentence_candidates:
            if pass_idx >= len(candidates):
                continue
            target = candidates[pass_idx]
            front = re.sub(rf"\b{re.escape(target)}\b", "____", sentence, count=1)
            key = front.casefold()
            if key in seen_fronts:
                continue
            seen_fronts.add(key)
            cards.append(Flashcard(front=front, back=target, topic=topic))
            progressed = True
            if len(cards) >= n:
                break
        if not progressed:
            break
        pass_idx += 1

    return cards


def generate_flashcards(
    topic: str,
    content: str = "",
    client: LLMClient | None = None,
    n: int = 10,
) -> list[Flashcard]:
    """Produce up to ``n`` flashcards about ``topic`` (grounded in ``content``)."""
    n = min(max(int(n), 1), 100)
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
