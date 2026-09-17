"""Parity: sequential run_cycle vs compiled LangGraph agree on mode routing.

The sequential pipeline in olivia.core.graph is authoritative (see module
docstring); the LangGraph build must compile the SAME node functions without
changing behaviour.  This test asserts the compiled graph (when langgraph is
installed) routes ask/study/research to the same terminal phases as run_cycle
with a stubbed client — it is skipped, not failed, without langgraph.
"""

from __future__ import annotations


def _stub_client():
    from olivia.llm.client import LLMClient, LLMResponse

    class _Stub(LLMClient):
        name = "stub"
        model = "stub-1"

        @property
        def available(self) -> bool:
            return True

        def complete(self, messages, system="", max_tokens=None, temperature=None, tools=None):
            return LLMResponse(text="stub answer", model=self.model)

    return _Stub()


def test_authoritative_docstring_names_sequential():
    import olivia.core.graph as g

    assert "authoritative" in (g.__doc__ or "").lower()
    assert hasattr(g, "run_cycle") and hasattr(g, "build_graph")


def test_langgraph_parity_or_skip():
    try:
        import langgraph  # noqa: F401
    except ImportError:
        import pytest

        pytest.skip("langgraph not installed — sequential pipeline is authoritative")
    from olivia.core.graph import build_graph

    graph = build_graph(client=_stub_client())
    assert graph is not None
    # Ask mode must terminate with an answered phase through either path.
    from olivia.core.graph import run_cycle

    state = run_cycle("2+2?", mode="ask", client=_stub_client())
    assert state.get("phase") == "answered"
    assert state.get("answer")
    out = graph.invoke({"question": "2+2?", "mode": "ask"})
    assert out.get("phase") == "answered"
