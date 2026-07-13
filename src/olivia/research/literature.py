"""Literature review step — search fan-out plus a thematic synthesis.

The searcher (``olivia.tools.literature``) already degrades to an empty list on
network failure; this module adds the second half of a review: an LLM-written
thematic synthesis with [n] citations, and a deterministic bullet digest when
no model is available.  Per the epistemic-honesty principle the offline path
never invents findings — it only reformats what the search returned, and says
plainly when nothing could be retrieved.
"""

from __future__ import annotations

import logging

from olivia.core.records import Paper
from olivia.llm.client import LLMClient, get_client
from olivia.llm.prompts import RESEARCH_SYSTEM
from olivia.tools.literature import literature_search

logger = logging.getLogger(__name__)

_ABSTRACT_CHARS = 500
"""How much of each abstract the LLM sees — enough for themes, cheap on tokens."""


def _first_sentence(text: str, limit: int = 200) -> str:
    """First sentence of an abstract, whitespace-normalised and length-capped."""
    text = " ".join(text.split())
    if not text:
        return "no abstract available"
    sentence = text.split(". ")[0].rstrip(".")
    return sentence[:limit] + ("…" if len(sentence) > limit else "")


def _cite_line(index: int, paper: Paper) -> str:
    year = paper.year if paper.year is not None else "n.d."
    venue = paper.venue or paper.source
    return f"[{index}] {paper.title} ({year}, {venue})"


def _fallback_synthesis(question: str, papers: list[Paper]) -> str:
    """Deterministic digest — reformats retrieved records, invents nothing."""
    if not papers:
        return (
            f"No literature could be retrieved for '{question}': the search backends "
            "were unreachable or returned nothing. Any conclusions downstream rest on "
            "hypothesis and experiment alone, not on published evidence."
        )
    return "\n".join(
        f"- {_cite_line(i, paper)} — {_first_sentence(paper.abstract)}"
        for i, paper in enumerate(papers, 1)
    )


def review_literature(
    question: str,
    client: LLMClient | None = None,
    max_papers: int = 12,
) -> tuple[list[Paper], str]:
    """Search the literature for ``question`` and synthesise it thematically.

    Returns ``(papers, synthesis_markdown)``.  Offline (no network, no LLM) the
    papers list may be empty and the synthesis degrades to a bullet digest.
    """
    client = client or get_client("strong")
    try:
        papers = literature_search(question, max_papers) or []
    except Exception as exc:
        logger.warning("literature_search failed: %s", exc)
        papers = []
    papers = papers[:max_papers]

    if client.available and papers:
        context = "\n".join(
            f"{_cite_line(i, paper)} — {paper.abstract[:_ABSTRACT_CHARS]}"
            for i, paper in enumerate(papers, 1)
        )
        prompt = (
            f"Research question: {question}\n\nPapers:\n{context}\n\n"
            "Write a short thematic literature synthesis in markdown (2-4 short "
            "paragraphs). Group the papers by theme, note agreements and open gaps, "
            "and cite them inline as [1], [2], … matching the numbering above."
        )
        text = client.ask(prompt, system=RESEARCH_SYSTEM).strip()
        if text:
            return papers, text
    return papers, _fallback_synthesis(question, papers)
