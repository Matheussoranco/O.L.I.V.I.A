"""Hypothesis generation — falsifiable by construction.

Every Hypothesis must carry observable predictions and a concrete refutation
test; :func:`is_falsifiable` enforces this symbolically, so unfalsifiable LLM
output is dropped rather than propagated.  Offline, a single low-confidence
template hypothesis keeps the cycle runnable end-to-end.
"""

from __future__ import annotations

import logging

from olivia.core.records import Hypothesis, Paper, new_id
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import RESEARCH_SYSTEM
from olivia.llm.structured import ask_json

logger = logging.getLogger(__name__)

_UNFALSIFIABLE_MARKERS = (
    "in every possible",
    "unmeasurable",
    "cannot be tested",
    "cannot be measured",
    "by definition true",
    "unobservable in principle",
)
"""Phrases that flag a statement as untestable; deliberately conservative."""


def is_falsifiable(h: Hypothesis) -> bool:
    """Symbolic Popper check: refutation test + predictions + testable wording."""
    if not h.falsification_test.strip() or not h.predictions:
        return False
    statement = h.statement.lower()
    return not any(marker in statement for marker in _UNFALSIFIABLE_MARKERS)


def _coerce(payload: dict, parent_id: str | None = None) -> Hypothesis | None:
    """Build a Hypothesis from untrusted LLM JSON; None when unusable."""
    if not isinstance(payload, dict):
        return None
    statement = str(payload.get("statement", "")).strip()
    if not statement:
        return None
    predictions = payload.get("predictions") or []
    if not isinstance(predictions, list):
        predictions = [str(predictions)]
    try:
        confidence = float(payload.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    return Hypothesis(
        statement=statement,
        rationale=str(payload.get("rationale", "")).strip(),
        predictions=[str(p).strip() for p in predictions if str(p).strip()],
        falsification_test=str(payload.get("falsification_test", "")).strip(),
        confidence=min(max(confidence, 0.0), 1.0),
        parent_id=parent_id,
    )


def generate_hypotheses(
    question: str,
    papers: list[Paper],
    client: LLMClient | None = None,
    max_hypotheses: int = 3,
) -> list[Hypothesis]:
    """Propose up to ``max_hypotheses`` falsifiable hypotheses for a question."""
    client = client or get_client("strong")

    if client.available:
        context = "\n".join(
            f"[{i}] {p.title} ({p.year}) — {p.abstract[:300]}" for i, p in enumerate(papers[:10], 1)
        )
        prompt = (
            f"Research question: {question}\n\n"
            + (f"Relevant literature:\n{context}\n\n" if context else "")
            + f"Propose up to {max_hypotheses} competing scientific hypotheses as a JSON list. "
            'Each item: {"statement": str, "rationale": str, '
            '"predictions": [observable consequences that must hold if true], '
            '"falsification_test": "a concrete test that could REFUTE it", '
            '"confidence": 0..1}. Every hypothesis must be falsifiable.'
        )
        payload = ask_json(client, prompt, system=RESEARCH_SYSTEM)
        if isinstance(payload, dict):  # tolerate {"hypotheses": [...]} wrapping
            payload = payload.get("hypotheses", [])
        if isinstance(payload, list):
            hypotheses = [h for h in (_coerce(item) for item in payload) if h]
            falsifiable = [h for h in hypotheses if is_falsifiable(h)]
            if len(falsifiable) < len(hypotheses):
                logger.info(
                    "Dropped %d unfalsifiable hypotheses", len(hypotheses) - len(falsifiable)
                )
            if falsifiable:
                return falsifiable[:max_hypotheses]

    # Offline template — keeps the cycle runnable; confidence is honest (low).
    return [
        Hypothesis(
            statement=(
                "A single dominant, measurable factor accounts for most of the "
                f"variation in the outcome asked about in: {question}"
            ),
            rationale="Default parsimony baseline generated without an LLM backend.",
            predictions=[
                "Controlling the candidate factor produces a measurable change in the outcome."
            ],
            falsification_test=(
                "A controlled comparison where the candidate factor is varied and the "
                "outcome does not change beyond noise refutes this hypothesis."
            ),
            confidence=0.3,
        )
    ]


def revise_hypothesis(
    h: Hypothesis,
    critique: str,
    client: LLMClient | None = None,
) -> Hypothesis:
    """Return a revised child hypothesis addressing a critique."""
    client = client or get_client("strong")

    if client.available:
        prompt = (
            f"Original hypothesis:\n  statement: {h.statement}\n"
            f"  predictions: {h.predictions}\n"
            f"  falsification test: {h.falsification_test}\n\n"
            f"Critique to address:\n{critique}\n\n"
            "Revise the hypothesis to fix the critique while staying falsifiable. "
            'Respond as JSON: {"statement": str, "rationale": str, '
            '"predictions": [str], "falsification_test": str, "confidence": 0..1}.'
        )
        payload = ask_json(client, prompt, system=RESEARCH_SYSTEM)
        revised = _coerce(payload, parent_id=h.id) if payload else None
        if revised and is_falsifiable(revised):
            return revised

    return Hypothesis(
        id=new_id("hyp"),
        statement=h.statement,
        rationale=(h.rationale + f"\nRevised after critique: {critique[:300]}").strip(),
        predictions=list(h.predictions),
        falsification_test=h.falsification_test,
        confidence=max(h.confidence - 0.1, 0.05),
        parent_id=h.id,
    )
