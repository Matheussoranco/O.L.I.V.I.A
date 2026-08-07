"""Study-tool correctness — scheduling, grading, and generation fidelity.

Three independent things are measured, because they fail independently:

1. **SM-2 scheduling** against :mod:`olivia.eval.sm2_reference`, an
   implementation written from the published algorithm that imports nothing
   from ``olivia.study.srs``. Every state after every grade is compared, so the
   lapse path (``q < 3``) is scored as thoroughly as the happy path.
2. **Quiz grading**, over the answer forms a learner actually types.
3. **Generation fidelity** — the question the harness cares about is not "did a
   card come out?" but "does the card test the source material, and is its
   answer actually in the source?" A generated card that shows its own answer
   is scored as a failure however well-formed it is.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from olivia.core.records import Flashcard, QuizQuestion
from olivia.eval.harness import (
    CaseResult,
    Metric,
    SuiteReport,
    load_dataset,
    ratio,
    register_suite,
)
from olivia.eval.sm2_reference import SM2State, review
from olivia.llm.client import LLMClient, NullClient

_EPSILON = 1e-9
_FIXED_TODAY = date(2026, 1, 1)
"""Scheduling is compared on a fixed day so the run is reproducible."""


# ---------------------------------------------------------------------------
# 1. SM-2 scheduling
# ---------------------------------------------------------------------------


def _close(left: float, right: float) -> bool:
    return abs(float(left) - float(right)) <= _EPSILON


def _sm2_cases() -> tuple[list[CaseResult], list[Metric], list[str]]:
    from olivia.study.srs import review_card

    data = load_dataset("sm2_sequences")
    cases: list[CaseResult] = []
    notes: list[str] = []
    steps_total = steps_matching = 0
    ease_bad = interval_bad = reps_bad = due_bad = 0
    lapse_steps = lapse_matching = 0

    for sequence in data["sequences"]:
        grades: list[int] = sequence["grades"]
        card = Flashcard(front="q", back="a", topic="eval")
        state = SM2State()
        mismatches: list[str] = []

        for index, quality in enumerate(grades, 1):
            card = review_card(card, quality, today=_FIXED_TODAY)
            state = review(state, quality)
            is_lapse = quality < 3

            ease_ok = _close(card.ease, state.ease)
            interval_ok = _close(card.interval_days, state.interval_days)
            reps_ok = card.repetitions == state.repetitions
            expected_due = (_FIXED_TODAY + timedelta(days=state.interval_days)).isoformat()
            due_ok = card.due == expected_due

            step_ok = ease_ok and interval_ok and reps_ok and due_ok
            steps_total += 1
            steps_matching += int(step_ok)
            ease_bad += int(not ease_ok)
            interval_bad += int(not interval_ok)
            reps_bad += int(not reps_ok)
            due_bad += int(not due_ok)
            if is_lapse:
                lapse_steps += 1
                lapse_matching += int(step_ok)

            if not step_ok:
                mismatches.append(
                    f"step {index} (q={quality}): "
                    f"ease {card.ease:.4f} vs {state.ease:.4f}, "
                    f"interval {card.interval_days:g} vs {state.interval_days:g}, "
                    f"reps {card.repetitions} vs {state.repetitions}"
                )

        cases.append(
            CaseResult(
                id=sequence["id"],
                outcome="correct" if not mismatches else "wrong",
                group="sm2",
                expected="matches SM-2 reference at every step",
                got="exact" if not mismatches else f"{len(mismatches)} divergent steps",
                detail="; ".join(mismatches[:3]),
                meta={"grades": grades, "note": sequence.get("note", "")},
            )
        )

    exact = sum(1 for c in cases if c.outcome == "correct")
    metrics = [
        Metric("sm2.sequence_exact", ratio(exact, len(cases)), len(cases), "all steps match"),
        Metric("sm2.step_exact", ratio(steps_matching, steps_total), steps_total, "per-review"),
        Metric("sm2.lapse_step_exact", ratio(lapse_matching, lapse_steps), lapse_steps, "q<3 only"),
        Metric("sm2.ease_exact", ratio(steps_total - ease_bad, steps_total), steps_total),
        Metric("sm2.interval_exact", ratio(steps_total - interval_bad, steps_total), steps_total),
        Metric("sm2.repetitions_exact", ratio(steps_total - reps_bad, steps_total), steps_total),
        Metric("sm2.due_exact", ratio(steps_total - due_bad, steps_total), steps_total),
    ]
    if interval_bad:
        notes.append(
            f"SM-2 interval diverged from the reference on {interval_bad}/{steps_total} reviews"
        )
    return cases, metrics, notes


# ---------------------------------------------------------------------------
# 2. Quiz grading
# ---------------------------------------------------------------------------


def _grading_cases() -> tuple[list[CaseResult], list[Metric]]:
    from olivia.study.quiz import grade_quiz

    data = load_dataset("quiz_grading")
    cases: list[CaseResult] = []
    for item in data["cases"]:
        spec = item["question"]
        options = list(spec.get("options", []))
        question = QuizQuestion(
            prompt=spec.get("prompt", ""),
            options=options,
            answer_index=spec.get("answer_index") if options else None,
            answer_text=spec.get("answer_text", ""),
        )
        graded = grade_quiz([question], [item["given"]])
        got = graded["results"][0]["correct"]
        expected = item["expect_correct"]
        cases.append(
            CaseResult(
                id=item["id"],
                outcome="correct" if got is expected else "wrong",
                group="quiz_grading",
                expected=str(expected),
                got=str(got),
                detail=item.get("note", ""),
                meta={"given": item["given"]},
            )
        )
    passed = sum(1 for c in cases if c.outcome == "correct")
    return cases, [Metric("grading.accuracy", ratio(passed, len(cases)), len(cases))]


# ---------------------------------------------------------------------------
# 3. Generation fidelity
# ---------------------------------------------------------------------------


def _word_present(needle: str, haystack: str) -> bool:
    """Whole-word, case-insensitive containment."""
    if not needle.strip():
        return False
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack, re.IGNORECASE) is not None


def _score_card(card: Flashcard, source: str) -> dict[str, bool]:
    front, back = card.front, card.back
    restored = front.replace("____", back, 1)
    return {
        "blank_present": front.count("____") == 1,
        "answer_in_source": _word_present(back, source),
        "answer_not_in_front": not _word_present(back, front),
        "front_grounded": bool(back) and _word_present(restored, source),
    }


def _fidelity_cases(client: LLMClient) -> tuple[list[CaseResult], list[Metric], list[str]]:
    from olivia.study.flashcards import generate_flashcards
    from olivia.study.quiz import generate_quiz

    data = load_dataset("study_sources")
    requested = 6
    cases: list[CaseResult] = []
    notes: list[str] = []
    checks: dict[str, list[bool]] = {}
    produced = wanted = 0
    duplicate_decks = 0
    quiz_total = quiz_clean = 0

    for source in data["sources"]:
        text, topic = source["text"], source["topic"]
        cards = generate_flashcards(topic, content=text, client=client, n=requested)
        produced += len(cards)
        wanted += requested
        if len({c.front for c in cards}) != len(cards):
            duplicate_decks += 1

        for index, card in enumerate(cards, 1):
            scored = _score_card(card, text)
            for key, value in scored.items():
                checks.setdefault(key, []).append(value)
            failures = [k for k, v in scored.items() if not v]
            cases.append(
                CaseResult(
                    id=f"{source['id']}-card{index}",
                    outcome="correct" if not failures else "wrong",
                    group="flashcard_fidelity",
                    expected="tests the source, answer hidden",
                    got=f"front={card.front!r} back={card.back!r}",
                    detail=("fails: " + ", ".join(failures)) if failures else "",
                    meta=scored,
                )
            )

        questions = generate_quiz(topic, content=text, client=client, n=requested)
        for index, question in enumerate(questions, 1):
            answer = (
                question.options[question.answer_index or 0]
                if question.options
                else question.answer_text
            )
            leaked = bool(answer) and answer.casefold() in question.prompt.casefold()
            quiz_total += 1
            quiz_clean += int(not leaked)
            cases.append(
                CaseResult(
                    id=f"{source['id']}-quiz{index}",
                    outcome="wrong" if leaked else "correct",
                    group="quiz_fidelity",
                    expected="prompt does not contain its own answer",
                    got=question.prompt[:80],
                    detail="answer appears verbatim in the prompt" if leaked else "",
                    meta={"leaked": leaked},
                )
            )

    metrics = [
        Metric("generation.card_yield", ratio(produced, wanted), wanted, "cards per card requested")
    ]
    metrics += [
        Metric(f"generation.{name}", ratio(sum(values), len(values)), len(values))
        for name, values in sorted(checks.items())
    ]
    metrics.append(
        Metric(
            "generation.deck_unique_fronts",
            ratio(len(data["sources"]) - duplicate_decks, len(data["sources"])),
            len(data["sources"]),
        )
    )
    metrics.append(
        Metric(
            "generation.quiz_answer_not_in_prompt",
            ratio(quiz_clean, quiz_total),
            quiz_total,
            "question does not give away its answer",
        )
    )
    if quiz_total and not quiz_clean:
        notes.append(
            "every offline quiz question contains its own expected answer verbatim: "
            "the prompt quotes the source sentence and answer_text is that same sentence"
        )
    leaking = [
        c for c in cases if c.group == "flashcard_fidelity" and not c.meta["answer_not_in_front"]
    ]
    if leaking:
        notes.append(
            f"{len(leaking)} cloze cards still show their answer in the front "
            "(str.replace substitutes only the first occurrence)"
        )
    return cases, metrics, notes


# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


def run(client: LLMClient | None = None) -> SuiteReport:
    report = SuiteReport(suite="study")

    sm2_cases, sm2_metrics, sm2_notes = _sm2_cases()
    grading_cases, grading_metrics = _grading_cases()
    # Fidelity is scored on the deterministic offline generator: NullClient
    # forces the cloze/open-question path, which is what ships without a key.
    offline_cases, offline_metrics, offline_notes = _fidelity_cases(NullClient())

    report.cases = sm2_cases + grading_cases + offline_cases
    report.metrics = sm2_metrics + grading_metrics + offline_metrics
    report.notes = sm2_notes + offline_notes

    if client is None or not client.available:
        report.notes.append("LLM-generated card fidelity not measured: no LLM backend configured")
        report.metrics.append(Metric("generation.llm_measured", 0.0, 0, "no LLM backend"))
        return report

    llm_cases, llm_metrics, llm_notes = _fidelity_cases(client)
    for case in llm_cases:
        case.id = f"{case.id}@llm"
        case.group = f"llm_{case.group}"
    report.cases += llm_cases
    report.metrics += [
        Metric(m.name.replace("generation.", "generation.llm_"), m.value, m.n, m.note)
        for m in llm_metrics
    ]
    report.notes += llm_notes
    report.metrics.append(Metric("generation.llm_measured", 1.0, len(llm_cases), "cases scored"))
    return report


register_suite("study", run)
