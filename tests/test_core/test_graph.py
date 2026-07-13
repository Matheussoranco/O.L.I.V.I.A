"""Cognitive cycle — ask / research / study end-to-end, fully offline."""

from __future__ import annotations

import pytest

from olivia.core.graph import _merge, build_graph, run_cycle
from olivia.core.records import DiscoveryReport
from olivia.core.state import make_initial_state
from olivia.llm.client import NullClient

_STATS_QUESTION = "What sample size do I need to detect an effect size of 0.5?"


def test_merge_appends_lists_and_replaces_scalars():
    state = make_initial_state("q")
    _merge(state, {"errors": ["one"], "phase": "a"})
    _merge(state, {"errors": ["two"], "phase": "b"})
    assert state["errors"] == ["one", "two"]
    assert state["phase"] == "b"


def test_run_cycle_ask_routes_through_experts():
    state = run_cycle(_STATS_QUESTION, mode="ask", client=NullClient())
    assert state["phase"] == "answered"
    assert state["answer_expert"] == "stats"
    assert "63" in state["answer"]
    assert state["errors"] == []


def test_run_cycle_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown mode"):
        run_cycle("q", mode="dream", client=NullClient())


def test_run_cycle_research_offline_full_loop():
    state = run_cycle("Does spacing improve retention?", mode="research", client=NullClient())

    # 1 template hypothesis + 2 revision children (max_revisions = 2).
    assert len(state["hypotheses"]) == 3
    assert len(state["experiments"]) == 3
    assert len(state["analyses"]) == 3
    assert state["iteration"] == 2
    assert state["needs_revision"]  # template designs keep failing the critic

    # Lineage: each revision child points at its parent.
    parents = [h.parent_id for h in state["hypotheses"]]
    assert parents[0] is None
    assert parents[1] == state["hypotheses"][0].id
    assert parents[2] == state["hypotheses"][1].id

    report = state["report"]
    assert isinstance(report, DiscoveryReport)
    assert state["answer"] == report.report_markdown
    assert "0 of 3 hypotheses" in report.conclusion
    assert state["errors"] == []


def test_run_cycle_research_records_outcome_and_notebook():
    from olivia.memory import Notebook
    from olivia.meta import get_meta_learner

    run_cycle("Does spacing improve retention?", mode="research", client=NullClient())

    stats = get_meta_learner().stats()
    assert "cycle:research" in stats["by_task"]["research"]

    discoveries = Notebook().entries("discovery")
    assert len(discoveries) == 1
    assert "spacing" in discoveries[0]["content"]


def test_run_cycle_study_offline_scaffold():
    state = run_cycle("linear algebra", mode="study", client=NullClient())
    assert state["study_plan"] is not None
    assert "# Study plan: linear algebra" in state["answer"]
    # Offline with no source content there is honestly nothing to build from.
    assert state["flashcards"] == []
    assert state["quiz"] == []


def test_run_cycle_ask_records_meta_outcome():
    from olivia.meta import get_meta_learner

    run_cycle(_STATS_QUESTION, mode="ask", client=NullClient())
    stats = get_meta_learner().stats()
    assert "cycle:ask" in stats["by_task"]["ask"]  # the cycle itself
    assert "stats" in stats["by_task"]["ask"]  # and the expert attempt


def test_build_graph_optional_langgraph():
    graph = build_graph(client=NullClient())
    if graph is None:  # langgraph not installed — sequential pipeline is authoritative
        return
    state = graph.invoke(make_initial_state(_STATS_QUESTION, "ask"))
    assert "63" in state["answer"]
