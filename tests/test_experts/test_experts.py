"""Mixture-of-Experts — symbolic scoring, honest offline answers, routing."""

from __future__ import annotations

import importlib.util

from olivia.core.records import Paper
from olivia.experts import answer, get_experts  # noqa: F401 — public API must import
from olivia.experts.base import ExpertAnswer, keyword_score
from olivia.experts.code_expert import CodeExpert
from olivia.experts.general_expert import GeneralExpert
from olivia.experts.literature_expert import LiteratureExpert
from olivia.experts.math_expert import MathExpert
from olivia.experts.router import route
from olivia.experts.stats_expert import StatsExpert
from olivia.llm.client import NullClient

_HAS_SYMPY = importlib.util.find_spec("sympy") is not None

_STATS_QUESTION = "What sample size do I need to detect an effect size of 0.5?"


def test_keyword_score_additive_and_capped():
    assert keyword_score("nothing relevant", ["alpha"]) == 0.0
    assert keyword_score("alpha beta", ["alpha", "beta"]) == 0.5
    assert keyword_score("a b c d e", ["a", "b", "c", "d", "e"]) == 0.95  # capped


# ---------------------------------------------------------------------------
# Individual experts
# ---------------------------------------------------------------------------


def test_math_expert_scores_math_questions_higher():
    expert = MathExpert()
    assert expert.score("solve x**2 - 4 = 0") > expert.score("who wrote Hamlet?")


def test_math_expert_symbolic_or_honest():
    result = MathExpert().answer("solve x**2 - 4 = 0", client=NullClient())
    if _HAS_SYMPY:
        assert result.confidence == 0.9
        assert "2" in result.answer
    else:
        assert result.confidence == 0.0
        assert "no LLM backend" in result.answer


def test_stats_expert_computes_sample_size_symbolically():
    result = StatsExpert().answer(_STATS_QUESTION, client=NullClient())
    assert result.confidence == 0.9
    assert "63" in result.answer
    assert result.details["n_per_group"] == 63


def test_stats_expert_offline_without_effect_size_abstains():
    result = StatsExpert().answer("Is my correlation significant?", client=NullClient())
    assert result.confidence == 0.0


def test_code_expert_runs_fenced_code_on_request():
    question = "Run this:\n```python\nprint(6 * 7)\n```"
    result = CodeExpert().answer(question, client=NullClient())
    assert result.confidence == 0.85
    assert "42" in result.answer


def test_code_expert_reports_execution_failure():
    question = "Execute:\n```python\nraise ValueError('nope')\n```"
    result = CodeExpert().answer(question, client=NullClient())
    assert result.details.get("ok") is False
    assert "nope" in result.answer


def test_literature_expert_honest_when_retrieval_empty():
    result = LiteratureExpert().answer("papers on spaced repetition", client=NullClient())
    assert result.confidence == 0.2
    assert "No citations can be offered" in result.answer


def test_literature_expert_cites_retrieved_papers(monkeypatch):
    from olivia.tools import literature

    paper = Paper(title="Spacing Effects", year=2020, source="arxiv")
    monkeypatch.setitem(literature._SOURCES, "arxiv", lambda q, n: [paper])
    monkeypatch.setitem(literature._SOURCES, "crossref", lambda q, n: [])
    monkeypatch.setitem(literature._SOURCES, "semanticscholar", lambda q, n: [])

    result = LiteratureExpert().answer("papers on spacing", client=NullClient())
    assert result.confidence == 0.8
    assert "Spacing Effects" in result.answer
    assert result.details["papers"] == ["Spacing Effects"]


def test_general_expert_is_floor_and_honest_offline():
    expert = GeneralExpert()
    assert expert.score("anything at all") == 0.2
    result = expert.answer("anything", client=NullClient())
    assert result.confidence == 0.0
    assert "No LLM backend is configured" in result.answer


# ---------------------------------------------------------------------------
# Routing and the cascade
# ---------------------------------------------------------------------------


def test_route_prefers_the_matching_specialist():
    ranked = route(_STATS_QUESTION)
    names = [expert.name for expert, _ in ranked]
    assert names[0] == "stats"
    assert names.index("stats") < names.index("general")


def test_route_blends_in_metalearner_history():
    from olivia.meta import get_meta_learner

    question = "an utterly neutral question"
    baseline = {e.name: s for e, s in route(question)}
    for _ in range(20):
        get_meta_learner().record("ask", "code", True)
    boosted = {e.name: s for e, s in route(question)}
    assert boosted["code"] > baseline["code"]  # history moved the blend


def test_answer_cascade_returns_confident_specialist_and_records():
    from olivia.meta import get_meta_learner

    result = answer(_STATS_QUESTION, client=NullClient())
    assert result.expert == "stats"
    assert "63" in result.answer
    assert get_meta_learner().stats()["total"] >= 1  # outcome was recorded


def test_answer_offline_unanswerable_returns_best_attempt():
    result = answer("Tell me something interesting.", client=NullClient())
    assert isinstance(result, ExpertAnswer)
    # Nothing clears the cascade threshold offline; the best sub-threshold
    # attempt wins (the literature expert's honest 0.2 beats general's 0.0).
    assert result.confidence < 0.35
    assert result.answer


def test_answer_single_mode_uses_only_top_expert():
    result = answer(_STATS_QUESTION, client=NullClient(), mode="single")
    assert result.expert == "stats"
