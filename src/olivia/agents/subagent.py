"""SubAgent — a role-typed Hermes agent with a filtered tool registry.

The Nous Hermes recipe: same model, different system prompt and tool
allowance per role.  Unknown roles raise (a programming error); a missing LLM
does not (HermesAgent already returns an error AgentResult offline).
"""

from __future__ import annotations

from olivia.agents.roles import ROLES, RoleSpec
from olivia.llm.client import LLMClient, get_client
from olivia.llm.hermes import AgentResult, HermesAgent
from olivia.tools import ToolRegistry, build_default_registry


def _filtered_registry(source: ToolRegistry, spec: RoleSpec) -> ToolRegistry:
    """A registry containing only the tools the role is allowed."""
    registry = ToolRegistry()
    if spec.tool_names is None:
        allowed = source.list()
    else:
        allowed = [t for name in spec.tool_names if (t := source.get(name)) is not None]
    for tool in allowed:
        registry.register(tool)
    return registry


class SubAgent:
    """One role-typed agent instance."""

    def __init__(
        self,
        role: str,
        client: LLMClient | None = None,
        registry: ToolRegistry | None = None,
        max_turns: int | None = None,
    ) -> None:
        spec = ROLES.get(role)
        if spec is None:
            raise ValueError(f"unknown role '{role}' (known: {sorted(ROLES)})")
        self.spec = spec
        self.client = client or get_client()
        self.registry = _filtered_registry(registry or build_default_registry(), spec)
        self._agent = HermesAgent(
            client=self.client,
            registry=self.registry,
            system_prompt=spec.system_prompt,
            max_turns=max_turns or spec.max_turns,
        )

    def run(self, task: str, context: str = "") -> AgentResult:
        """Execute one task; offline this returns AgentResult(error=...)."""
        return self._agent.run(task, context)
