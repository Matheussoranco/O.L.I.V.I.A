"""Spaced repetition — the SM-2 algorithm over JSON-persisted decks.

SM-2 (SuperMemo 2) is symbolic and battle-tested; no LLM is involved in
scheduling.  Decks live as plain JSON under ``~/.olivia/decks`` so they are
portable and hand-editable.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path

from olivia.core.records import Flashcard

logger = logging.getLogger(__name__)

_MIN_EASE = 1.3


def slugify(text: str) -> str:
    """Filesystem-safe slug: lowercase, non-alphanumerics collapsed to '-'."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "deck"


def review_card(card: Flashcard, quality: int, today: date | None = None) -> Flashcard:
    """Apply one SM-2 review (quality 0–5) and return an updated copy."""
    quality = max(0, min(5, int(quality)))
    today = today or date.today()

    if quality < 3:
        repetitions, interval, ease = 0, 1.0, card.ease
    else:
        repetitions = card.repetitions + 1
        if repetitions == 1:
            interval = 1.0
        elif repetitions == 2:
            interval = 6.0
        else:
            interval = float(round(card.interval_days * card.ease))
        ease = max(
            _MIN_EASE, card.ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
        )

    return dataclasses.replace(
        card,
        ease=ease,
        interval_days=interval,
        repetitions=repetitions,
        due=(today + timedelta(days=interval)).isoformat(),
    )


class Deck:
    """A topic's flashcards with JSON persistence and due-date queries."""

    def __init__(self, topic: str, root: Path | None = None) -> None:
        from olivia.config import settings

        self.topic = topic
        self.path = (root or settings.data_dir() / "decks") / f"{slugify(topic)}.json"
        self.cards: list[Flashcard] = []
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.cards = [Flashcard(**item) for item in raw]
            except Exception as exc:
                logger.warning("Could not load deck %s: %s", self.path, exc)

    def add(self, cards: list[Flashcard]) -> int:
        """Add cards, deduplicating by casefolded front text; returns count added."""
        known = {c.front.casefold().strip() for c in self.cards}
        added = 0
        for card in cards:
            key = card.front.casefold().strip()
            if key and key not in known:
                self.cards.append(card)
                known.add(key)
                added += 1
        if added:
            self.save()
        return added

    def due(self, today: date | None = None) -> list[Flashcard]:
        """Cards never reviewed or whose due date has arrived."""
        cutoff = (today or date.today()).isoformat()
        return [c for c in self.cards if not c.due or c.due <= cutoff]

    def review(self, card_id: str, quality: int) -> Flashcard | None:
        """Grade one card by id; persists and returns the updated card."""
        for i, card in enumerate(self.cards):
            if card.id == card_id:
                self.cards[i] = review_card(card, quality)
                self.save()
                return self.cards[i]
        return None

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [dataclasses.asdict(c) for c in self.cards]
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return self.path
