"""Study package: spaced repetition, flashcards, quizzes, planning, tutoring."""

from olivia.study.flashcards import generate_flashcards
from olivia.study.planner import make_study_plan, plan_to_markdown
from olivia.study.quiz import generate_quiz, grade_quiz
from olivia.study.srs import Deck, review_card, slugify
from olivia.study.tutor import TutorSession

__all__ = [
    "Deck",
    "TutorSession",
    "generate_flashcards",
    "generate_quiz",
    "grade_quiz",
    "make_study_plan",
    "plan_to_markdown",
    "review_card",
    "slugify",
]
