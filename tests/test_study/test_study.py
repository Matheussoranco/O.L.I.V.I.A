"""Study package — SM-2 scheduling, decks, cards, quizzes, plans, tutor."""

from __future__ import annotations

import json
from datetime import date

from olivia.core.records import Flashcard, QuizQuestion
from olivia.llm.client import NullClient
from olivia.study import (
    Deck,
    TutorSession,
    generate_flashcards,
    generate_quiz,
    grade_quiz,
    make_study_plan,
    plan_to_markdown,
    review_card,
)
from olivia.study.srs import slugify

_TODAY = date(2026, 1, 1)

_CONTENT = (
    "Spaced repetition schedules reviews at increasing intervals to exploit the "
    "spacing effect. The SM-2 algorithm adjusts each card's ease factor after "
    "every review. Cards answered poorly return to the start of the schedule."
)


# ---------------------------------------------------------------------------
# SM-2
# ---------------------------------------------------------------------------


def test_sm2_first_three_perfect_reviews():
    card = Flashcard(front="f", back="b")

    card = review_card(card, 5, today=_TODAY)
    assert (card.repetitions, card.interval_days) == (1, 1.0)
    assert card.due == "2026-01-02"

    card = review_card(card, 5, today=_TODAY)
    assert (card.repetitions, card.interval_days) == (2, 6.0)

    card = review_card(card, 5, today=_TODAY)
    assert card.repetitions == 3
    assert card.interval_days == round(6.0 * 2.6)  # ease grew to 2.6 after two q=5 reviews


def test_sm2_lapse_resets_schedule_not_ease_floor():
    card = Flashcard(front="f", back="b", repetitions=3, interval_days=15.0, ease=2.5)
    lapsed = review_card(card, 1, today=_TODAY)
    assert (lapsed.repetitions, lapsed.interval_days) == (0, 1.0)
    assert lapsed.ease == 2.5  # lapse does not change ease in SM-2


def test_sm2_ease_never_drops_below_floor():
    card = Flashcard(front="f", back="b", ease=1.3)
    for _ in range(5):
        card = review_card(card, 3, today=_TODAY)  # q=3 pushes ease down each time
    assert card.ease == 1.3


def test_sm2_quality_is_clamped():
    card = review_card(Flashcard(front="f", back="b"), 99, today=_TODAY)
    assert card.repetitions == 1  # treated as q=5, not an error


# ---------------------------------------------------------------------------
# Deck persistence
# ---------------------------------------------------------------------------


def test_slugify():
    assert slugify("Quantum Mechanics!") == "quantum-mechanics"
    assert slugify("???") == "deck"


def test_deck_add_dedupes_and_persists():
    deck = Deck("Quantum Mechanics")
    cards = [
        Flashcard(front="What is ħ?", back="Reduced Planck constant"),
        Flashcard(front="what is ħ?  ", back="duplicate by casefolded front"),
        Flashcard(front="Define ket.", back="A vector in Hilbert space"),
    ]
    assert deck.add(cards) == 2

    reloaded = Deck("Quantum Mechanics")
    assert len(reloaded.cards) == 2
    assert reloaded.path == deck.path
    assert reloaded.path.name == "quantum-mechanics.json"


def test_deck_due_and_review_roundtrip():
    deck = Deck("topic")
    deck.add([Flashcard(front="q1", back="a1")])
    due = deck.due(today=_TODAY)
    assert len(due) == 1  # never-reviewed cards are due immediately

    updated = deck.review(due[0].id, 5)
    assert updated is not None and updated.repetitions == 1
    assert deck.due(today=_TODAY) == []  # now scheduled in the future
    assert Deck("topic").cards[0].repetitions == 1  # persisted

    assert deck.review("card_missing", 5) is None


def test_deck_corrupt_file_starts_empty(tmp_path):
    root = tmp_path / "decks"
    root.mkdir()
    (root / "broken.json").write_text("{not json", encoding="utf-8")
    assert Deck("broken", root=root).cards == []


# ---------------------------------------------------------------------------
# Flashcards
# ---------------------------------------------------------------------------


def test_flashcards_offline_cloze_from_content():
    cards = generate_flashcards("srs", content=_CONTENT, client=NullClient(), n=2)
    assert len(cards) == 2
    for card in cards:
        assert "____" in card.front
        assert card.back  # the blanked word
        assert card.back not in card.front.replace("____", "")


def test_flashcards_offline_without_content_returns_nothing():
    assert generate_flashcards("srs", client=NullClient()) == []


def test_flashcards_from_llm_json(fake_client):
    payload = [
        {"front": "What is SM-2?", "back": "A spaced-repetition algorithm"},
        {"front": "", "back": "dropped — empty front"},
    ]
    cards = generate_flashcards("srs", client=fake_client(json.dumps(payload)))
    assert len(cards) == 1
    assert cards[0].topic == "srs"


# ---------------------------------------------------------------------------
# Quiz
# ---------------------------------------------------------------------------


def test_quiz_offline_open_questions_from_content():
    questions = generate_quiz("srs", content=_CONTENT, client=NullClient(), n=2)
    assert len(questions) == 2
    assert all(q.options == [] for q in questions)


def test_quiz_llm_mcq_validation(fake_client):
    payload = [
        {"prompt": "Pick.", "options": ["a", "b", "c", "d"], "answer_index": 2},
        {"prompt": "Bad index.", "options": ["a", "b"], "answer_index": 5},
    ]
    questions = generate_quiz("t", client=fake_client(json.dumps(payload)))
    assert len(questions) == 1  # out-of-range answer_index is rejected


def test_grade_quiz_accepts_index_letter_and_text():
    q = QuizQuestion(prompt="?", options=["red", "green", "blue"], answer_index=1)
    graded = grade_quiz([q, q, q, q], ["1", "b", "GREEN", "red"])
    corrects = [r["correct"] for r in graded["results"]]
    assert corrects == [True, True, True, False]
    assert graded["score"] == 3 and graded["graded"] == 4
    assert graded["percent"] == 75.0


def test_grade_quiz_open_mismatch_is_ungraded_not_wrong():
    q = QuizQuestion(prompt="Explain X.", answer_text="the reference answer")
    graded = grade_quiz([q, q], ["my own words", "The reference answer"])
    assert [r["correct"] for r in graded["results"]] == [None, True]
    assert graded["graded"] == 1 and graded["score"] == 1


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


def test_study_plan_offline_scaffold_arc():
    plan = make_study_plan("statistics", weeks=4, client=NullClient())
    assert plan.weeks == 4 and len(plan.milestones) == 4
    assert plan.milestones[0]["title"].startswith("Foundations")
    assert plan.milestones[-1]["title"] == "Review and capstone"

    markdown = plan_to_markdown(plan)
    assert "# Study plan: statistics" in markdown
    assert "## Week 1" in markdown and "## Week 4" in markdown


def test_study_plan_from_llm_json(fake_client):
    payload = {
        "prerequisites": ["algebra"],
        "milestones": [
            {"week": 1, "title": "Basics", "objectives": ["o1"], "practice": "p1"},
            {"week": 2, "title": "Depth", "objectives": ["o2"], "practice": "p2"},
        ],
        "resources": ["book"],
    }
    plan = make_study_plan("stats", weeks=5, client=fake_client(json.dumps(payload)))
    assert plan.weeks == 2  # trusts the milestones actually returned
    assert plan.prerequisites == ["algebra"]


# ---------------------------------------------------------------------------
# Tutor
# ---------------------------------------------------------------------------


def test_tutor_offline_is_honest():
    session = TutorSession("recursion", client=NullClient())
    reply = session.respond("I think recursion is a loop?")
    assert "No LLM backend is configured" in reply
    assert "recursion" in session.suggest_question()
    assert len(session.messages) == 2  # user + assistant recorded


def test_tutor_with_llm_keeps_history(fake_client):
    client = fake_client("What happens at the base case?", "Good — and without one?")
    session = TutorSession("recursion", client=client)
    assert session.respond("hello") == "What happens at the base case?"
    assert session.respond("it stops") == "Good — and without one?"
    assert len(session.messages) == 4
    assert len(client.calls[1]) == 3  # second call saw the running history
