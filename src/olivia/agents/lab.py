"""ResearchLab — a multi-agent seminar: draft, attack, synthesise.

Three roles argue so one answer improves: the researcher drafts an evidence-
based investigation, the critic attacks its weakest links, and the writer
synthesises a final position that answers the critique.  Additional rounds
feed the synthesis back to the researcher for revision.
"""

from __future__ import annotations

import logging

from olivia.agents.subagent import SubAgent
from olivia.llm.client import LLMClient, get_client

logger = logging.getLogger(__name__)


class ResearchLab:
    """Researcher → critic → writer, optionally iterated."""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or get_client()

    def investigate(self, question: str, rounds: int = 1) -> dict:
        """Run the seminar; returns draft/critique/synthesis plus a transcript."""
        result = {
            "question": question,
            "draft": "",
            "critique": "",
            "synthesis": "",
            "transcript": [],
            "error": "",
        }
        if not self.client.available:
            result["error"] = "llm unavailable"
            return result

        researcher = SubAgent("researcher", client=self.client)
        critic = SubAgent("critic", client=self.client)
        writer = SubAgent("writer", client=self.client)

        draft = ""
        for round_number in range(1, max(1, rounds) + 1):
            draft_task = (
                f"Investigate: {question}\n"
                "Search the literature where useful; state what is established, "
                "what is hypothesis, and what is unknown."
            )
            if draft:
                draft_task += (
                    f"\n\nRevise your previous draft to answer this critique:\n{result['critique']}"
                )
            drafted = researcher.run(draft_task)
            if drafted.error:
                result["error"] = drafted.error
                return result
            draft = drafted.answer
            result["transcript"].append({"role": "researcher", "content": draft})

            criticised = critic.run(
                f"Question: {question}\n\nDraft under review:\n{draft}\n\n"
                "Attack the weakest links; propose the smallest fixes."
            )
            result["transcript"].append({"role": "critic", "content": criticised.answer})
            result["critique"] = criticised.answer
            logger.info("ResearchLab round %d complete", round_number)

        written = writer.run(
            f"Question: {question}\n\nDraft:\n{draft}\n\nCritique:\n{result['critique']}\n\n"
            "Write the final synthesis: answer the question, incorporate the valid "
            "criticism, and mark remaining uncertainty explicitly."
        )
        result["draft"] = draft
        result["synthesis"] = written.answer
        result["transcript"].append({"role": "writer", "content": written.answer})
        return result
