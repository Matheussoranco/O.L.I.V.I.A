"""Agents — Hermes tool-calling loop, role filtering, pool, and the lab."""

from __future__ import annotations

import pytest

from olivia.agents import AgentPool, ResearchLab, SubAgent
from olivia.llm.client import NullClient
from olivia.llm.hermes import HermesAgent, parse_tool_calls, strip_think
from olivia.tools.registry import Tool, ToolRegistry


def _echo_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="Echo the text back.",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}},
            fn=lambda text: f"echo:{text}",
        )
    )
    return registry


# ---------------------------------------------------------------------------
# Hermes protocol primitives
# ---------------------------------------------------------------------------


def test_parse_tool_calls_tolerates_malformed_json():
    text = (
        '<tool_call>\n{"name": "echo", "arguments": {"text": "hi"}}\n</tool_call>\n'
        "<tool_call>\n{broken json}\n</tool_call>\n"
        '<tool_call>\n{"arguments": {"no": "name"}}\n</tool_call>'
    )
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "echo" and calls[0].arguments == {"text": "hi"}


def test_parse_tool_calls_wraps_non_dict_arguments():
    calls = parse_tool_calls('<tool_call>{"name": "echo", "arguments": "hi"}</tool_call>')
    assert calls[0].arguments == {"value": "hi"}


def test_strip_think_separates_reasoning_from_answer():
    visible, thoughts = strip_think("<think>private chain</think>The answer is 4.")
    assert visible == "The answer is 4."
    assert thoughts == "private chain"


# ---------------------------------------------------------------------------
# HermesAgent loop
# ---------------------------------------------------------------------------


def test_hermes_agent_executes_tool_then_answers(fake_client):
    client = fake_client(
        "<think>need the echo</think>\n"
        '<tool_call>\n{"name": "echo", "arguments": {"text": "hi"}}\n</tool_call>',
        "The echo said hi.",
    )
    agent = HermesAgent(client=client, registry=_echo_registry())
    result = agent.run("say hi via the tool")

    assert result.error == ""
    assert result.answer == "The echo said hi."
    assert result.turns == 2
    assert [c.name for c in result.tool_calls] == ["echo"]
    assert "need the echo" in result.reasoning
    # The tool's real output was fed back inside a <tool_response> block.
    tool_feedback = result.transcript[2]["content"]
    assert "<tool_response>" in tool_feedback and "echo:hi" in tool_feedback


def test_hermes_agent_offline_returns_error():
    agent = HermesAgent(client=NullClient(), registry=_echo_registry())
    assert agent.run("anything").error == "llm unavailable"


def test_hermes_agent_max_turns_exceeded(fake_client):
    looping = '<tool_call>{"name": "echo", "arguments": {"text": "again"}}</tool_call>'
    agent = HermesAgent(client=fake_client(looping), registry=_echo_registry(), max_turns=2)
    result = agent.run("loop forever")
    assert result.error == "max turns exceeded"
    assert result.turns == 2


# ---------------------------------------------------------------------------
# SubAgent roles
# ---------------------------------------------------------------------------


def test_subagent_unknown_role_raises():
    with pytest.raises(ValueError, match="unknown role"):
        SubAgent("wizard", client=NullClient())


def test_subagent_registry_is_filtered_by_role():
    researcher = SubAgent("researcher", client=NullClient())
    assert researcher.registry.names() == ["fetch_url", "literature_search"]

    experimenter = SubAgent("experimenter", client=NullClient())
    assert set(experimenter.registry.names()) == {
        "python_exec",
        "sample_size",
        "stats_test",
        "symbolic_math",
    }

    critic = SubAgent("critic", client=NullClient())
    assert critic.registry.names() == []  # judgement roles get no tools


def test_subagent_offline_run_degrades():
    result = SubAgent("researcher", client=NullClient()).run("investigate")
    assert result.error == "llm unavailable"


# ---------------------------------------------------------------------------
# AgentPool
# ---------------------------------------------------------------------------


def test_agent_pool_preserves_order_and_isolates_failures():
    pool = AgentPool(client=NullClient())
    results = pool.run_parallel([("researcher", "a"), ("wizard", "b"), ("critic", "c")])
    assert len(results) == 3
    assert results[0].error == "llm unavailable"
    assert "unknown role" in results[1].error  # bad slot fails alone
    assert results[2].error == "llm unavailable"
    assert pool.run_parallel([]) == []


# ---------------------------------------------------------------------------
# ResearchLab
# ---------------------------------------------------------------------------


def test_research_lab_offline_says_so():
    result = ResearchLab(client=NullClient()).investigate("why sleep?")
    assert result["error"] == "llm unavailable"
    assert result["synthesis"] == ""


def test_research_lab_seminar_flow(fake_client):
    client = fake_client("Draft: spacing helps.", "Critique: cite evidence.", "Synthesis: final.")
    result = ResearchLab(client=client).investigate("does spacing help?", rounds=1)

    assert result["error"] == ""
    assert result["draft"] == "Draft: spacing helps."
    assert result["critique"] == "Critique: cite evidence."
    assert result["synthesis"] == "Synthesis: final."
    assert [t["role"] for t in result["transcript"]] == ["researcher", "critic", "writer"]
    # The writer was shown both the draft and the critique.
    writer_prompt = client.calls[-1][0]["content"]
    assert "Draft: spacing helps." in writer_prompt
    assert "Critique: cite evidence." in writer_prompt


def test_research_lab_second_round_feeds_critique_back(fake_client):
    client = fake_client("D1", "C1", "D2", "C2", "S")
    result = ResearchLab(client=client).investigate("q", rounds=2)
    assert result["draft"] == "D2" and result["critique"] == "C2"
    revision_prompt = client.calls[2][0]["content"]
    assert "C1" in revision_prompt  # round-2 researcher saw round-1's critique
