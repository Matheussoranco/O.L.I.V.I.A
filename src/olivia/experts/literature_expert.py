"""Literature expert — real retrieval over arXiv/Crossref/S2, cited answers.

Retrieval failure is reported as such (low confidence), never papered over
with remembered citations the model can't verify.
"""

from __future__ import annotations

import logging

from olivia.experts.base import Expert, ExpertAnswer, keyword_score
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import RESEARCH_SYSTEM

logger = logging.getLogger(__name__)

_KEYWORDS = [
    "paper", "papers", "literature", "cite", "citation", "published",
    "state of the art", "survey", "arxiv", "doi", "study", "studies", "research on",
]


class LiteratureExpert(Expert):
    name = "literature"
    description = "Scientific literature search and synthesis with real citations."

    def score(self, question: str) -> float:
        return keyword_score(question, _KEYWORDS)

    def answer(self, question: str, client: LLMClient | None = None) -> ExpertAnswer:
        try:
            from olivia.tools.literature import literature_search

            papers = literature_search(question, max_results=8)
        except Exception as exc:
            logger.warning("literature retrieval failed: %s", exc)
            papers = []

        if not papers:
            return ExpertAnswer(
                expert=self.name,
                answer="Literature retrieval failed or returned nothing — the search "
                "backends may be unreachable. No citations can be offered.",
                confidence=0.2,
            )

        listing = "\n".join(
            f"- {p.title} ({p.year or 'n.d.'}, {p.venue or p.source}) {p.url}".rstrip()
            for p in papers
        )
        answer = f"Relevant literature:\n{listing}"

        client = client or get_client()
        if client.available:
            context = "\n".join(
                f"[{i}] {p.title} ({p.year}) — {p.abstract[:300]}"
                for i, p in enumerate(papers, 1)
            )
            synthesis = client.ask(
                f"Question: {question}\n\nPapers:\n{context}\n\n"
                "In 2-3 sentences, synthesise what these papers say about the question, "
                "citing [n].",
                system=RESEARCH_SYSTEM,
            ).strip()
            if synthesis:
                answer = f"{synthesis}\n\n{answer}"

        return ExpertAnswer(
            expert=self.name,
            answer=answer,
            confidence=0.8,
            details={"papers": [p.title for p in papers]},
        )
