"""The cognitive cycle — route a question through ask / research / study.

The sequential pipeline below is the authoritative implementation; when
langgraph is installed, :func:`build_graph` compiles the same node functions
into a StateGraph (checkpointing, streaming, LangGraph Studio) without
changing behaviour.  Every node reads and returns ``OliviaState`` deltas.

Research runs the Claude-for-Science loop with Popperian revision: critique
findings feed hypothesis revision up to ``settings.research.max_revisions``
times before the report is written.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from olivia.core.state import Mode, OliviaState, make_initial_state
from olivia.llm.client import LLMClient, get_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Nodes (state → state delta)
# ---------------------------------------------------------------------------


def node_ask(state: OliviaState, client: LLMClient | None = None) -> dict[str, Any]:
    """Answer directly through the Mixture-of-Experts."""
    from olivia.experts import answer as moe_answer

    result = moe_answer(state.get("question", ""), client=client)
    return {"answer": result.answer, "answer_expert": result.expert, "phase": "answered"}


def node_literature(state: OliviaState, client: LLMClient | None = None) -> dict[str, Any]:
    from olivia.config import settings
    from olivia.research import review_literature

    papers, synthesis = review_literature(
        state.get("question", ""), client=client, max_papers=settings.research.max_papers
    )
    return {
        "papers": papers,
        "critique": "",
        "phase": "literature",
        "messages": [{"role": "assistant", "content": f"Literature review:\n{synthesis}"}],
    }


def node_hypotheses(state: OliviaState, client: LLMClient | None = None) -> dict[str, Any]:
    from olivia.config import settings
    from olivia.research import generate_hypotheses

    hypotheses = generate_hypotheses(
        state.get("question", ""),
        state.get("papers", []),
        client=client,
        max_hypotheses=settings.research.max_hypotheses,
    )
    return {"hypotheses": hypotheses, "phase": "hypotheses"}


def node_experiments(state: OliviaState, client: LLMClient | None = None) -> dict[str, Any]:
    from olivia.research import design_experiment

    experimented = {e.hypothesis_id for e in state.get("experiments", [])}
    plans = [
        design_experiment(h, client=client)
        for h in state.get("hypotheses", [])
        if h.status == "proposed" and h.id not in experimented
    ]
    return {"experiments": plans, "phase": "experiments"}


def node_analysis(state: OliviaState, client: LLMClient | None = None) -> dict[str, Any]:
    from olivia.research import run_analysis

    analysed = {a.experiment_id for a in state.get("analyses", [])}
    analyses = [
        run_analysis(plan, client=client)
        for plan in state.get("experiments", [])
        if plan.id not in analysed
    ]
    return {"analyses": analyses, "phase": "analysis"}


def node_critique(state: OliviaState, client: LLMClient | None = None) -> dict[str, Any]:
    from olivia.research import critique_research

    critique, needs_revision = critique_research(
        state.get("question", ""),
        state.get("hypotheses", []),
        state.get("experiments", []),
        state.get("analyses", []),
        client=client,
    )
    return {"critique": critique, "needs_revision": needs_revision, "phase": "critique"}


def node_revise(state: OliviaState, client: LLMClient | None = None) -> dict[str, Any]:
    """Revise the still-live hypotheses in place; children re-enter the loop."""
    from olivia.research import revise_hypothesis

    revised = []
    for h in state.get("hypotheses", []):
        if h.status == "proposed":
            h.status = "revised"
            revised.append(revise_hypothesis(h, state.get("critique", ""), client=client))
    return {"hypotheses": revised, "iteration": state.get("iteration", 0) + 1, "phase": "revise"}


def node_report(state: OliviaState, client: LLMClient | None = None) -> dict[str, Any]:
    from olivia.research import write_report

    report = write_report(
        state.get("question", ""),
        state.get("papers", []),
        state.get("hypotheses", []),
        state.get("experiments", []),
        state.get("analyses", []),
        critique=state.get("critique", ""),
        client=client,
    )
    return {"report": report, "answer": report.report_markdown, "phase": "report"}


def node_study(state: OliviaState, client: LLMClient | None = None) -> dict[str, Any]:
    from olivia.study import generate_flashcards, generate_quiz, make_study_plan, plan_to_markdown

    topic = state.get("question", "")
    plan = make_study_plan(topic, client=client)
    flashcards = generate_flashcards(topic, client=client)
    quiz = generate_quiz(topic, client=client)
    return {
        "study_plan": plan,
        "flashcards": flashcards,
        "quiz": quiz,
        "answer": plan_to_markdown(plan),
        "phase": "study",
    }


# ---------------------------------------------------------------------------
# Sequential pipeline (authoritative)
# ---------------------------------------------------------------------------


def _merge(state: OliviaState, delta: dict[str, Any]) -> None:
    """Apply a node delta using the state's append/replace semantics."""
    for key, value in delta.items():
        if key in (
            "messages",
            "errors",
            "papers",
            "hypotheses",
            "experiments",
            "analyses",
            "flashcards",
            "quiz",
        ):
            state.setdefault(key, []).extend(value)  # type: ignore[typeddict-item]
        else:
            state[key] = value  # type: ignore[literal-required]


def run_cycle(
    question: str,
    mode: Mode | str = "ask",
    client: LLMClient | None = None,
) -> OliviaState:
    """Run one full cognitive cycle and return the final state."""
    from olivia.config import settings

    client = client or get_client()
    state = make_initial_state(question, mode)
    started = time.perf_counter()

    try:
        if mode == "ask":
            _merge(state, node_ask(state, client))
        elif mode == "study":
            _merge(state, node_study(state, client))
        elif mode == "research":
            _merge(state, node_literature(state, client))
            _merge(state, node_hypotheses(state, client))
            for _ in range(settings.research.max_revisions + 1):
                _merge(state, node_experiments(state, client))
                _merge(state, node_analysis(state, client))
                _merge(state, node_critique(state, client))
                if not state.get("needs_revision"):
                    break
                if state.get("iteration", 0) >= settings.research.max_revisions:
                    break
                _merge(state, node_revise(state, client))
            _merge(state, node_report(state, client))
        else:
            raise ValueError(f"unknown mode '{mode}' (use ask | research | study)")
    except ValueError:
        raise
    except Exception as exc:
        logger.exception("cycle failed")
        state.setdefault("errors", []).append(str(exc))

    _record_outcome(state, mode, time.perf_counter() - started)
    return state


def _record_outcome(state: OliviaState, mode: str, duration_s: float) -> None:
    """Feed the MetaLearner and lab notebook; both are best-effort."""
    success = bool(state.get("answer")) and not state.get("errors")
    try:
        from olivia.meta import get_meta_learner

        get_meta_learner().record(str(mode), f"cycle:{mode}", success, duration_s)
    except Exception as exc:
        logger.debug("meta record failed: %s", exc)
    if mode == "research" and state.get("report"):
        try:
            from olivia.memory import Notebook

            report = state["report"]
            Notebook().add(
                "discovery",
                f"{report.question}\n\n{report.conclusion}",
                tags=["research"],
                meta={"confidence": report.confidence},
            )
        except Exception as exc:
            logger.debug("notebook record failed: %s", exc)


# ---------------------------------------------------------------------------
# Optional LangGraph build
# ---------------------------------------------------------------------------


def build_graph(client: LLMClient | None = None):
    """Compile the same nodes into a LangGraph StateGraph; None if not installed."""
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return None

    from olivia.config import settings

    client = client or get_client()

    def wrap(fn):
        return lambda state: fn(state, client)

    graph = StateGraph(OliviaState)
    graph.add_node("ask", wrap(node_ask))
    graph.add_node("literature", wrap(node_literature))
    graph.add_node("hypotheses", wrap(node_hypotheses))
    graph.add_node("experiments", wrap(node_experiments))
    graph.add_node("analysis", wrap(node_analysis))
    graph.add_node("critique", wrap(node_critique))
    graph.add_node("revise", wrap(node_revise))
    graph.add_node("report", wrap(node_report))
    graph.add_node("study", wrap(node_study))

    graph.set_conditional_entry_point(
        lambda state: state.get("mode", "ask"),
        {"ask": "ask", "research": "literature", "study": "study"},
    )
    graph.add_edge("literature", "hypotheses")
    graph.add_edge("hypotheses", "experiments")
    graph.add_edge("experiments", "analysis")
    graph.add_edge("analysis", "critique")
    graph.add_conditional_edges(
        "critique",
        lambda state: (
            "revise"
            if state.get("needs_revision")
            and state.get("iteration", 0) < settings.research.max_revisions
            else "report"
        ),
        {"revise": "revise", "report": "report"},
    )
    graph.add_edge("revise", "experiments")
    graph.add_edge("report", END)
    graph.add_edge("ask", END)
    graph.add_edge("study", END)
    return graph.compile()
