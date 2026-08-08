"""An independent SM-2 reference, written from the published algorithm.

This module deliberately does **not** import anything from ``olivia.study.srs``.
It exists to be a second opinion: if the two implementations agree, the
agreement means something; if they diverge, the eval says where.

The algorithm (Wozniak, SuperMemo 2), for a review of quality ``q`` in 0..5:

1. ``I(1) := 1``
2. ``I(2) := 6``
3. ``I(n) := I(n-1) * EF`` for ``n > 2``, using the E-factor **as it stood
   before this review's update** (step 4 comes after step 3 in the published
   ordering).
4. ``EF' := EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))``
5. ``if EF' < 1.3 then EF' := 1.3``
6. ``if q < 3`` the item is relearned: the repetition count restarts and the
   next interval is 1 day.

Two points in the published description are genuinely ambiguous, so the choice
is stated here rather than hidden:

* **E-factor on a lapse.** Step 4 is written unconditionally ("after each
  repetition"), and the widely-copied reference implementations update ``EF``
  even when ``q < 3``. This reference does the same. A card that keeps failing
  must get harder to schedule.
* **Rounding.** The published recurrence is real-valued; schedulers need whole
  days. This reference rounds each interval half-**up**, the conventional
  reading of "round". Python's built-in ``round`` is half-to-**even**, so an
  interval landing exactly on ``.5`` is a real divergence between the two
  conventions, and the eval reports it instead of papering over it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_EASE = 1.3
INITIAL_EASE = 2.5


def round_half_up(value: float) -> float:
    """Round to the nearest whole day, halves away from zero.

    ``round()`` in Python is half-to-even: ``round(130.5) == 130``. Schedulers
    conventionally mean half-up. Keeping the reference explicit makes any
    divergence a finding rather than an accident.
    """
    return float(math.floor(value + 0.5)) if value >= 0 else float(math.ceil(value - 0.5))


@dataclass
class SM2State:
    """The scheduling state of a single card."""

    ease: float = INITIAL_EASE
    interval_days: float = 0.0
    repetitions: int = 0

    def as_tuple(self) -> tuple[float, float, int]:
        return (round(self.ease, 10), self.interval_days, self.repetitions)


def update_ease(ease: float, quality: int) -> float:
    """Step 4 + step 5 of the published algorithm."""
    updated = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    return max(MIN_EASE, updated)


def review(state: SM2State, quality: int) -> SM2State:
    """Apply one review and return the next state (the input is not mutated)."""
    if not 0 <= quality <= 5:
        raise ValueError(f"SM-2 quality must be 0..5, got {quality}")

    # Step 3 uses the E-factor as it stood *before* this review's update.
    ease_before = state.ease

    if quality < 3:
        repetitions = 0
        interval = 1.0
    else:
        repetitions = state.repetitions + 1
        if repetitions == 1:
            interval = 1.0
        elif repetitions == 2:
            interval = 6.0
        else:
            interval = round_half_up(state.interval_days * ease_before)

    return SM2State(
        ease=update_ease(ease_before, quality),
        interval_days=interval,
        repetitions=repetitions,
    )


def replay(grades: list[int]) -> list[SM2State]:
    """The state after each grade in a sequence, starting from a fresh card."""
    state = SM2State()
    history: list[SM2State] = []
    for quality in grades:
        state = review(state, quality)
        history.append(state)
    return history
