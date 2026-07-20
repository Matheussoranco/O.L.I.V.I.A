"""Study package: spaced repetition, flashcards, quizzes, planning, tutoring."""

from olivia.study.flashcards import generate_flashcards
from olivia.study.planner import make_study_plan, plan_to_markdown
from olivia.study.quiz import generate_quiz, grade_quiz
from olivia.study.solver import solution_to_markdown, solve_problem
from olivia.study.srs import Deck, review_card, slugify
from olivia.study.tutor import TutorSession
from olivia.study.worksheet import generate_worksheet, worksheet_to_markdown

__all__ = [
    "Deck",
    "TutorSession",
    "generate_flashcards",
    "generate_quiz",
    "generate_worksheet",
    "grade_quiz",
    "make_study_plan",
    "plan_to_markdown",
    "review_card",
    "slugify",
    "solution_to_markdown",
    "solve_problem",
    "worksheet_to_markdown",
]
