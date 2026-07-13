"""Quiz generation and grading — MCQs from an LLM, open questions offline.

Grading is symbolic and forgiving about answer form (index, letter, or the
option's text); open questions without a model to judge them are reported as
ungraded rather than guessed at.
"""

from __future__ import annotations

import logging
import re

from olivia.core.records import QuizQuestion
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import OLIVIA_PERSONA
from olivia.llm.structured import ask_json

logger = logging.getLogger(__name__)

_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]")
_DIFFICULTIES = ("easy", "medium", "hard")


def _coerce_question(item: object) -> QuizQuestion | None:
    if not isinstance(item, dict) or not str(item.get("prompt", "")).strip():
        return None
    options = [str(o).strip() for o in item.get("options", []) if str(o).strip()]
    answer_index = item.get("answer_index")
    if options and (
        not isinstance(answer_index, int) or not 0 <= answer_index < len(options)
    ):
        return None
    difficulty = str(item.get("difficulty", "medium")).lower()
    return QuizQuestion(
        prompt=str(item["prompt"]).strip(),
        options=options,
        answer_index=answer_index if options else None,
        answer_text=str(item.get("answer_text", "")).strip(),
        explanation=str(item.get("explanation", "")).strip(),
        difficulty=difficulty if difficulty in _DIFFICULTIES else "medium",  # type: ignore[arg-type]
    )


def generate_quiz(
    topic: str,
    content: str = "",
    client: LLMClient | None = None,
    n: int = 5,
) -> list[QuizQuestion]:
    """Produce up to ``n`` quiz questions about ``topic``."""
    client = client or get_client()

    if client.available:
        prompt = (
            f"Write up to {n} multiple-choice quiz questions about: {topic}\n"
            + (f"\nGround them in this material:\n{content[:6000]}\n" if content else "")
            + '\nRespond as a JSON list of {"prompt": str, "options": [exactly 4 strings], '
            '"answer_index": 0-3, "explanation": "why the answer is right", '
            '"difficulty": "easy|medium|hard"}. Distractors must be plausible.'
        )
        payload = ask_json(client, prompt, system=OLIVIA_PERSONA, max_tokens=2500)
        if isinstance(payload, dict):
            payload = payload.get("questions", [])
        if isinstance(payload, list):
            questions = [q for q in map(_coerce_question, payload) if q]
            if questions:
                return questions[:n]

    # Offline: open questions built from the learner's own material.
    questions = []
    for match in _SENTENCE_RE.finditer(content):
        sentence = " ".join(match.group().split())
        if not 30 <= len(sentence) <= 300:
            continue
        questions.append(
            QuizQuestion(
                prompt=f"Explain in your own words: what does this describe? — “{sentence}”",
                answer_text=sentence,
            )
        )
        if len(questions) >= n:
            break
    if not questions:
        logger.warning("generate_quiz: no LLM and no content — nothing to build from")
    return questions


def grade_quiz(questions: list[QuizQuestion], answers: list[str]) -> dict:
    """Grade answers against questions; open questions may come back ungraded."""
    results: list[dict] = []
    score = graded = 0

    for question, given in zip(questions, answers, strict=False):
        given = (given or "").strip()
        correct: bool | None
        if question.options:
            expected = question.options[question.answer_index or 0]
            matches_text = given.casefold() == expected.casefold()
            matches_index = given.isdigit() and int(given) == question.answer_index
            correct = False
            if matches_text or matches_index:
                correct = True
            elif len(given) == 1 and given.isalpha():
                correct = ord(given.lower()) - ord("a") == question.answer_index
        else:
            expected = question.answer_text
            # Free-form answers that don't match exactly are ungraded, not wrong.
            matched = bool(expected) and given.casefold() == expected.strip().casefold()
            correct = True if matched else None
        if correct is not None:
            graded += 1
            score += int(correct)
        results.append(
            {
                "id": question.id,
                "correct": correct,
                "expected": expected,
                "given": given,
                "explanation": question.explanation,
            }
        )

    return {
        "score": score,
        "graded": graded,
        "total": len(questions),
        "percent": round(100 * score / graded, 1) if graded else 0.0,
        "results": results,
    }
