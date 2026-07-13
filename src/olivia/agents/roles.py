"""Role specs — who a sub-agent is and which tools it may touch.

``tool_names=None`` grants the full registry; ``[]`` grants none.  Critics,
writers, and tutors get no tools on purpose: their value is judgement, and a
tool-less agent cannot wander.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from olivia.llm.prompts import (
    CRITIC_SYSTEM,
    RESEARCH_SYSTEM,
    TUTOR_SYSTEM,
    WRITER_SYSTEM,
)

_EXPERIMENTER_ADDENDUM = """
You design and RUN experiments: prefer writing a small simulation with
python_exec over speculating, size samples with sample_size, and test
differences with stats_test. Print one final JSON object from any simulation.
"""


@dataclass
class RoleSpec:
    """A named sub-agent role: persona plus tool allowance."""

    name: str
    system_prompt: str
    tool_names: list[str] | None = field(default=None)
    """None = every registry tool; [] = no tools at all."""
    max_turns: int = 8


ROLES: dict[str, RoleSpec] = {
    "researcher": RoleSpec(
        name="researcher",
        system_prompt=RESEARCH_SYSTEM,
        tool_names=["literature_search", "fetch_url"],
    ),
    "experimenter": RoleSpec(
        name="experimenter",
        system_prompt=RESEARCH_SYSTEM + _EXPERIMENTER_ADDENDUM,
        tool_names=["python_exec", "stats_test", "sample_size", "symbolic_math"],
    ),
    "critic": RoleSpec(name="critic", system_prompt=CRITIC_SYSTEM, tool_names=[]),
    "writer": RoleSpec(name="writer", system_prompt=WRITER_SYSTEM, tool_names=[]),
    "tutor": RoleSpec(name="tutor", system_prompt=TUTOR_SYSTEM, tool_names=[]),
}
