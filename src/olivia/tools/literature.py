"""Literature search — arXiv, Crossref, and Semantic Scholar over plain httpx.

No API keys required; every function degrades to an empty list on network
failure so the research cycle keeps running offline (the LLM then reasons from
its own knowledge and says so, per the epistemic-honesty principle).
"""

from __future__ import annotations

import inspect
import ipaddress
import logging
import re
import socket
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from olivia.core.records import Paper

if TYPE_CHECKING:
    from olivia.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0
_UA = {"User-Agent": "olivia-research-agent/0.1 (mailto:matheussoranco@gmail.com)"}

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"


def _network_enabled(allow_network: bool | None) -> bool:
    if allow_network is not None:
        return allow_network
    from olivia.config import settings

    return settings.network_enabled


def _safe_url(url: str) -> bool:
    """Reject non-web, credential-bearing, and private-network destinations."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        return False
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
            )
        }
    except OSError:
        return False
    return all(
        not (ip := ipaddress.ip_address(address)).is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
        for address in addresses
    )


def _get(url: str, params: dict | None = None, allow_network: bool | None = None) -> object | None:
    """One guarded GET; returns the httpx.Response or None."""
    import httpx

    if not _network_enabled(allow_network) or not _safe_url(url):
        logger.info("network request blocked by policy: %s", url)
        return None
    try:
        response = httpx.get(
            url, params=params, headers=_UA, timeout=_TIMEOUT, follow_redirects=False
        )
        response.raise_for_status()
        return response
    except Exception as exc:
        logger.warning("GET %s failed: %s", url, exc)
        return None


def _request(url: str, params: dict, allow_network: bool | None) -> object | None:
    """Call the low-level fetcher compatibly with test/custom source adapters."""
    if allow_network is None:
        return _get(url, params)
    return _get(url, params, allow_network=allow_network)


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------


def search_arxiv(
    query: str, max_results: int = 10, allow_network: bool | None = None
) -> list[Paper]:
    """Search the arXiv Atom API."""
    response = _request(
        "https://export.arxiv.org/api/query",
        {"search_query": f"all:{query}", "max_results": max_results, "sortBy": "relevance"},
        allow_network,
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


def search_crossref(
    query: str, max_results: int = 10, allow_network: bool | None = None
) -> list[Paper]:
    """Search the Crossref works API (peer-reviewed venues, DOIs, citations)."""
    response = _request(
        "https://api.crossref.org/works",
        {
            "query": query,
            "rows": max_results,
            "select": "title,author,issued,abstract,URL,DOI,container-title,is-referenced-by-count",
        },
        allow_network,
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


def search_semanticscholar(
    query: str, max_results: int = 10, allow_network: bool | None = None
) -> list[Paper]:
    """Search the Semantic Scholar Graph API (free tier, rate-limited)."""
    response = _request(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        {
            "query": query,
            "limit": max_results,
            "fields": "title,authors,year,abstract,url,externalIds,venue,citationCount",
        },
        allow_network,
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

# Allowlist of literature backends. Only these source names are honored;
# anything else in `sources` is silently dropped (defense against prompt-
# injected source names pointing at attacker hosts). Network itself is gated
# by settings.network_enabled / allow_network + _safe_url (no private nets).
_SOURCE_ALLOWLIST = frozenset({"arxiv", "crossref", "semanticscholar"})

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
    allow_network: bool | None = None,
) -> list[Paper]:
    """Fan out across sources concurrently, dedupe by DOI/title, rank by citations."""
    from concurrent.futures import ThreadPoolExecutor

    max_results = min(max(int(max_results), 1), 100)
    chosen = [s for s in (sources or list(_SOURCES)) if s in _SOURCES and s in _SOURCE_ALLOWLIST]
    per_source = max(3, max_results // max(len(chosen), 1) + 2)

    with ThreadPoolExecutor(max_workers=len(chosen) or 1) as pool:
        futures = []
        for source_name in chosen:
            source = _SOURCES[source_name]
            accepts_policy = "allow_network" in inspect.signature(source).parameters
            if accepts_policy:
                futures.append(pool.submit(source, query, per_source, allow_network=allow_network))
            else:
                futures.append(pool.submit(source, query, per_source))
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


def fetch_url(url: str, max_chars: int = 20000, allow_network: bool | None = None) -> str:
    """Fetch a URL and return readable plain text (bs4 when installed)."""
    max_chars = min(max(int(max_chars), 100), 100_000)
    response = _get(url) if allow_network is None else _get(url, allow_network=allow_network)
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
                    "max_results": {
                        "type": "integer",
                        "default": 12,
                        "minimum": 1,
                        "maximum": 100,
                    },
                    "allow_network": {"type": "boolean", "default": False},
                },
                "required": ["query"],
            },
            fn=lambda query, max_results=12, allow_network=False: [
                to_dict(p)
                for p in literature_search(query, max_results, allow_network=allow_network)
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
                    "max_chars": {
                        "type": "integer",
                        "default": 20000,
                        "minimum": 100,
                        "maximum": 100000,
                    },
                    "allow_network": {"type": "boolean", "default": False},
                },
                "required": ["url"],
            },
            fn=fetch_url,
            risk=1,
        )
    )
