"""Tests for Socratic interactive tutor mode (T5 / #13)."""

from __future__ import annotations

import json
from typing import Any

from typer.testing import CliRunner

from olivia.__main__ import app
from olivia.llm.client import LLMClient, LLMResponse, NullClient
from olivia.study import TutorSession, summary_to_markdown


class RecordingTutorClient(LLMClient):
    """Fake LLM client that records both messages and system prompts."""

    name = "recording-fake"

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses) or [""]
        self.calls: list[dict[str, Any]] = []

    @property
    def available(self) -> bool:
        return True

    def complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": list(messages), "system": system, "max_tokens": max_tokens})
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return LLMResponse(text=self._responses[idx], model="recording-fake")


def test_tutor_socratic_protocol_and_state_tracking() -> None:
    client = RecordingTutorClient(
        "What stays constant for every inertial observer in special relativity?",
        "Close! Light speed is constant, not time itself — what happens to a moving clock?",
        "Hint: compare the path of a light beam bouncing vertically inside a moving train.",
        json.dumps(
            {
                "covered": ["Constancy of light speed", "Time dilation"],
                "misconceptions_addressed": ["Assumed time is absolute across inertial frames"],
                "next_steps": ["Derive the Lorentz factor gamma from the light-clock triangle."],
            }
        ),
    )
    session = TutorSession("special relativity", client=client)

    opener = session.suggest_question()
    assert "special relativity" in opener
    assert session.state.opening_question == opener
    assert session.state.turns == 0
    assert session.messages == []

    reply = session.respond("I think time is the same everywhere and light speed changes.")
    assert "moving clock" in reply
    assert session.state.turns == 1
    assert session.state.hints_used == 0
    assert "Opening question posed:" in client.calls[1]["system"]
    assert "turn=1" in client.calls[1]["system"]
    assert "Ask one focused guiding question at a time" in client.calls[1]["system"]

    hint = session.request_hint("light clock")
    assert "moving train" in hint
    assert session.state.hints_used == 1
    assert session.state.turns == 1
    assert "light clock" in client.calls[2]["messages"][-1]["content"]

    summary = session.summarize()
    assert summary.topic == "special relativity"
    assert summary.turns == 1
    assert summary.hints_used == 1
    assert summary.mode == "llm"
    assert "Time dilation" in summary.covered
    assert summary.misconceptions_addressed == ["Assumed time is absolute across inertial frames"]
    md = summary_to_markdown(summary)
    assert "## Tutor Session Summary: special relativity" in md
    assert "Assumed time is absolute across inertial frames" in md


def test_tutor_handle_input_commands_and_graceful_exit() -> None:
    client = RecordingTutorClient(
        "Good start — what makes a reference frame inertial?",
        "Hint: think about whether an unpushed puck accelerates on frictionless ice.",
        json.dumps(
            {
                "covered": ["Inertial frames"],
                "misconceptions_addressed": [],
                "next_steps": ["Contrast inertial and accelerating frames."],
            }
        ),
    )
    session = TutorSession("special relativity", client=client)

    out, done = session.handle_input("   ")
    assert (out, done) == ("", False)
    assert session.state.turns == 0

    help_text, done = session.handle_input("/help")
    assert not done
    assert "/hint" in help_text and "/exit" in help_text

    reply, done = session.handle_input("A frame moving at constant velocity.")
    assert not done
    assert "inertial" in reply
    assert session.state.turns == 1

    hint, done = session.handle_input("/hint")
    assert not done
    assert "frictionless ice" in hint
    assert session.state.hints_used == 1

    summary_md, done = session.handle_input("/exit")
    assert done is True
    assert session.state.ended is True
    assert "## Tutor Session Summary: special relativity" in summary_md
    assert "Inertial frames" in summary_md


def test_tutor_offline_hint_and_honest_summary() -> None:
    session = TutorSession("special relativity", client=NullClient())
    opener = session.suggest_question()
    assert "special relativity" in opener

    reply = session.respond("Speed of light is constant.")
    assert "No LLM backend is configured" in reply

    hint = session.request_hint()
    assert "No LLM backend is configured" in hint
    assert session.state.turns == 1
    assert session.state.hints_used == 1

    summary = session.summarize()
    assert summary.mode == "offline"
    assert summary.turns == 1
    assert summary.hints_used == 1
    assert any("OLIVIA_LLM__PROVIDER" in step for step in summary.next_steps)
    assert summary.misconceptions_addressed == []


def test_tutor_malformed_llm_summary_falls_back_cleanly(fake_client: Any) -> None:
    client = fake_client("What does c represent?", "not valid json at all")
    session = TutorSession("special relativity", client=client)
    session.respond("Speed of light in vacuum.")
    summary = session.summarize()
    assert summary.topic == "special relativity"
    assert summary.turns == 1
    assert summary.mode == "deterministic_fallback"
    assert summary.covered
    md = summary_to_markdown(summary)
    assert "deterministic_fallback" in md


def test_cli_tutor_interactive_session_with_exit_and_saved_summary(
    monkeypatch: Any, tmp_path: Any
) -> None:
    client = RecordingTutorClient(
        "What happens to simultaneity for two observers in relative motion?",
        (
            "Great question! Suppose lightning strikes both ends of a moving train — "
            "who sees both flashes together?"
        ),
        "Hint: light travels at the same speed c for both the platform and train observers.",
        json.dumps(
            {
                "covered": ["Relativity of simultaneity"],
                "misconceptions_addressed": ["Simultaneity is not frame-independent"],
                "next_steps": ["Sketch a spacetime diagram of the train thought experiment."],
            }
        ),
    )
    monkeypatch.setattr("olivia.study.tutor.get_client", lambda tier="default": client)

    out_file = tmp_path / "summary.md"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["tutor", "special relativity", "--output", str(out_file)],
        input="Aren't simultaneous events simultaneous for everyone?\n/hint\n/exit\n",
    )
    assert result.exit_code == 0, result.output
    assert "Tutor session: special relativity" in result.output
    assert "moving train" in result.output
    assert "Hint: light travels" in result.output
    assert "Tutor Session Summary: special relativity" in result.output
    assert out_file.exists()
    saved = out_file.read_text(encoding="utf-8")
    assert "Relativity of simultaneity" in saved
    assert "Simultaneity is not frame-independent" in saved


def test_cli_tutor_eof_exits_gracefully_with_summary() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["tutor", "special relativity"],
        input="My initial guess about frames.\n",
    )
    assert result.exit_code == 0, result.output
    assert "Tutor Session Summary: special relativity" in result.output
    assert "Turns:" in result.output


def test_cli_tutor_max_turns_stops_with_summary(monkeypatch: Any) -> None:
    client = RecordingTutorClient(
        "What is the first postulate of special relativity?",
        "Right — now what about the second postulate?",
        json.dumps(
            {
                "covered": ["First postulate of special relativity"],
                "misconceptions_addressed": [],
                "next_steps": ["Explore the second postulate (invariance of c)."],
            }
        ),
    )
    monkeypatch.setattr("olivia.study.tutor.get_client", lambda tier="default": client)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["tutor", "special relativity", "--max-turns", "1"],
        input="The laws of physics are the same in all inertial frames.\n",
    )
    assert result.exit_code == 0, result.output
    assert "second postulate" in result.output
    assert "Tutor Session Summary: special relativity" in result.output
