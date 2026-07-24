"""Literature search — arXiv, Crossref, and Semantic Scholar over plain httpx.

No API keys required; every function degrades to an empty list on network
failure so the research cycle keeps running offline (the LLM then reasons from
its own knowledge and says so, per the epistemic-honesty principle).
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from olivia.core.records import Paper

if TYPE_CHECKING:
    from olivia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0
_UA = {"User-Agent": "olivia-research-agent/0.1 (mailto:matheussoranco@gmail.com)"}

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"


def _get(url: str, params: dict | None = None) -> object | None:
    """One guarded GET; returns the httpx.Response or None."""
    import httpx

    try:
        response = httpx.get(
            url, params=params, headers=_UA, timeout=_TIMEOUT, follow_redirects=True
        )
        response.raise_for_status()
        return response
    except Exception as exc:
        logger.warning("GET %s failed: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------


def search_arxiv(query: str, max_results: int = 10) -> list[Paper]:
    """Search the arXiv Atom API."""
    response = _get(
        "https://export.arxiv.org/api/query",
        {"search_query": f"all:{query}", "max_results": max_results, "sortBy": "relevance"},
    )
    if response is None:
        return []
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        logger.warning("arXiv XML parse failed: %s", exc)
        return []

    papers: list[Paper] = []
    for entry in root.findall(f"{_ATOM}entry"):
        title = (entry.findtext(f"{_ATOM}title") or "").strip()
        if not title:
            continue
        published = entry.findtext(f"{_ATOM}published") or ""
        year = int(published[:4]) if published[:4].isdigit() else None
        papers.append(
            Paper(
                title=re.sub(r"\s+", " ", title),
                authors=[
                    (a.findtext(f"{_ATOM}name") or "").strip()
                    for a in entry.findall(f"{_ATOM}author")
                ],
                year=year,
                abstract=re.sub(r"\s+", " ", (entry.findtext(f"{_ATOM}summary") or "").strip()),
                url=(entry.findtext(f"{_ATOM}id") or "").strip(),
                doi=(entry.findtext(f"{_ARXIV}doi") or "").strip(),
                venue="arXiv",
                source="arxiv",
                keywords=[
                    c.get("term", "") for c in entry.findall(f"{_ATOM}category") if c.get("term")
                ],
            )
        )
    return papers


# ---------------------------------------------------------------------------
# Crossref
# ---------------------------------------------------------------------------

_JATS_TAG_RE = re.compile(r"<[^>]+>")


def search_crossref(query: str, max_results: int = 10) -> list[Paper]:
    """Search the Crossref works API (peer-reviewed venues, DOIs, citations)."""
    response = _get(
        "https://api.crossref.org/works",
        {
            "query": query,
            "rows": max_results,
            "select": "title,author,issued,abstract,URL,DOI,container-title,is-referenced-by-count",
        },
    )
    if response is None:
        return []
    try:
        items = response.json()["message"]["items"]
    except Exception as exc:
        logger.warning("Crossref JSON parse failed: %s", exc)
        return []

    papers: list[Paper] = []
    for item in items:
        titles = item.get("title") or []
        if not titles:
            continue
        date_parts = (item.get("issued") or {}).get("date-parts") or [[None]]
        year = date_parts[0][0] if date_parts[0] else None
        abstract = _JATS_TAG_RE.sub(" ", item.get("abstract", ""))
        papers.append(
            Paper(
                title=re.sub(r"\s+", " ", titles[0]).strip(),
                authors=[
                    " ".join(filter(None, [a.get("given"), a.get("family")]))
                    for a in item.get("author", [])
                ],
                year=year if isinstance(year, int) else None,
                abstract=re.sub(r"\s+", " ", abstract).strip(),
                url=item.get("URL", ""),
                doi=item.get("DOI", ""),
                venue=(item.get("container-title") or [""])[0],
                source="crossref",
                citations=item.get("is-referenced-by-count"),
            )
        )
    return papers


# ---------------------------------------------------------------------------
# Semantic Scholar
# ---------------------------------------------------------------------------


def search_semanticscholar(query: str, max_results: int = 10) -> list[Paper]:
    """Search the Semantic Scholar Graph API (free tier, rate-limited)."""
    response = _get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        {
            "query": query,
            "limit": max_results,
            "fields": "title,authors,year,abstract,url,externalIds,venue,citationCount",
        },
    )
    if response is None:
        return []
    try:
        items = response.json().get("data", [])
    except Exception as exc:
        logger.warning("Semantic Scholar JSON parse failed: %s", exc)
        return []

    papers: list[Paper] = []
    for item in items:
        if not item.get("title"):
            continue
        papers.append(
            Paper(
                title=item["title"].strip(),
                authors=[a.get("name", "") for a in item.get("authors", [])],
                year=item.get("year"),
                abstract=(item.get("abstract") or "").strip(),
                url=item.get("url", ""),
                doi=(item.get("externalIds") or {}).get("DOI", ""),
                venue=item.get("venue", ""),
                source="semanticscholar",
                citations=item.get("citationCount"),
            )
        )
    return papers


# ---------------------------------------------------------------------------
# Fan-out search + dedupe
# ---------------------------------------------------------------------------

_SOURCES = {
    "arxiv": search_arxiv,
    "crossref": search_crossref,
    "semanticscholar": search_semanticscholar,
}


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def _prefer(candidate: Paper, held: Paper) -> bool:
    """DOI-bearing records win; abstract richness breaks ties."""
    if bool(candidate.doi) != bool(held.doi):
        return bool(candidate.doi)
    return len(candidate.abstract) > len(held.abstract)


def literature_search(
    query: str,
    max_results: int = 12,
    sources: list[str] | None = None,
) -> list[Paper]:
    """Fan out across sources concurrently, dedupe by DOI/title, rank by citations."""
    from concurrent.futures import ThreadPoolExecutor

    chosen = [s for s in (sources or list(_SOURCES)) if s in _SOURCES]
    per_source = max(3, max_results // max(len(chosen), 1) + 2)

    with ThreadPoolExecutor(max_workers=len(chosen) or 1) as pool:
        futures = [pool.submit(_SOURCES[s], query, per_source) for s in chosen]
        batches = [f.result() for f in futures]

    seen: dict[str, Paper] = {}
    for paper in (p for batch in batches for p in batch):
        # Title is the merge key (sources disagree on DOI presence); DOI only
        # identifies records whose title is missing.
        key = _title_key(paper.title) or paper.doi.lower()
        if not key:
            continue
        held = seen.get(key)
        if held is None or _prefer(paper, held):
            seen[key] = paper

    ranked = sorted(seen.values(), key=lambda p: (p.citations or 0, p.year or 0), reverse=True)
    return ranked[:max_results]


# ---------------------------------------------------------------------------
# Page fetch
# ---------------------------------------------------------------------------

_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def fetch_url(url: str, max_chars: int = 20000) -> str:
    """Fetch a URL and return readable plain text (bs4 when installed)."""
    response = _get(url)
    if response is None:
        return ""
    html = response.text
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
    except ImportError:
        text = _TAG_RE.sub(" ", _SCRIPT_RE.sub(" ", html))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------


def register_tools(registry: ToolRegistry) -> None:
    from olivia.core.records import to_dict
    from olivia.tools.registry import Tool

    registry.register(
        Tool(
            name="literature_search",
            description=(
                "Search scientific literature across arXiv, Crossref, and Semantic "
                "Scholar. Returns deduplicated bibliographic records."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "default": 12},
                },
                "required": ["query"],
            },
            fn=lambda query, max_results=12: [
                to_dict(p) for p in literature_search(query, max_results)
            ],
            risk=1,
        )
    )
    registry.register(
        Tool(
            name="fetch_url",
            description="Fetch a web page and return its readable plain text.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 20000},
                },
                "required": ["url"],
            },
            fn=fetch_url,
            risk=1,
        )
    )
