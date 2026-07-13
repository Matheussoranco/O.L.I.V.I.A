"""AgentPool — run independent role/task pairs concurrently.

Thread-based because agent turns are I/O-bound (LLM and HTTP round-trips).
Results come back in submission order; a bad role yields an error result in
its slot instead of poisoning the batch.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from olivia.agents.subagent import SubAgent
from olivia.llm.client import LLMClient, get_client
from olivia.llm.hermes import AgentResult

logger = logging.getLogger(__name__)


class AgentPool:
    """Fan out (role, task) pairs to parallel SubAgents."""

    def __init__(self, client: LLMClient | None = None, max_workers: int = 4) -> None:
        self.client = client or get_client()
        self.max_workers = max_workers

    def _run_one(self, role: str, task: str) -> AgentResult:
        try:
            return SubAgent(role, client=self.client).run(task)
        except ValueError as exc:
            return AgentResult(error=str(exc))
        except Exception as exc:
            logger.warning("SubAgent %s failed: %s", role, exc)
            return AgentResult(error=str(exc))

    def run_parallel(self, tasks: list[tuple[str, str]]) -> list[AgentResult]:
        """Execute ``[(role, task), ...]``; results keep submission order."""
        if not tasks:
            return []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(tasks))) as pool:
            return list(pool.map(lambda pair: self._run_one(*pair), tasks))
