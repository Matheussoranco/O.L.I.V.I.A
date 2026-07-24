"""Literature tools — parsing, dedupe, and offline degradation (no network)."""

from __future__ import annotations

from olivia.core.records import Paper
from olivia.tools import literature

_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1234.5678v1</id>
    <published>2021-03-01T00:00:00Z</published>
    <title>Spaced   Repetition\n Works</title>
    <summary>It works.  Really well.</summary>
    <author><name>Ada Lovelace</name></author>
    <category term="cs.LG"/>
  </entry>
</feed>"""


class _FakeResponse:
    def __init__(self, text: str = "", payload=None):
        self.text = text
        self._payload = payload

    def json(self):
        return self._payload


def test_search_arxiv_parses_atom(monkeypatch):
    monkeypatch.setattr(literature, "_get", lambda url, params=None: _FakeResponse(_ARXIV_XML))
    papers = literature.search_arxiv("spaced repetition")
    assert len(papers) == 1
    paper = papers[0]
    assert paper.title == "Spaced Repetition Works"
    assert paper.year == 2021
    assert paper.authors == ["Ada Lovelace"]
    assert paper.source == "arxiv"
    assert paper.keywords == ["cs.LG"]


def test_search_offline_returns_empty(monkeypatch):
    monkeypatch.setattr(literature, "_get", lambda url, params=None: None)
    assert literature.search_arxiv("x") == []
    assert literature.search_crossref("x") == []
    assert literature.search_semanticscholar("x") == []


def test_literature_search_dedupes_and_ranks(monkeypatch):
    a = Paper(title="Same Title!", doi="", citations=1, abstract="short", source="arxiv")
    b = Paper(
        title="Same title",
        doi="10.1/x",
        citations=50,
        abstract="longer abstract",
        source="crossref",
    )
    c = Paper(title="Other work", citations=5, source="semanticscholar")
    monkeypatch.setitem(literature._SOURCES, "arxiv", lambda q, n: [a])
    monkeypatch.setitem(literature._SOURCES, "crossref", lambda q, n: [b])
    monkeypatch.setitem(literature._SOURCES, "semanticscholar", lambda q, n: [c])

    results = literature.literature_search("q", max_results=5)
    titles = [p.title for p in results]
    assert len(results) == 2  # a and b merged by title key
    assert titles[0] == "Same title"  # highest citations first; DOI version kept
    assert results[0].doi == "10.1/x"


def test_fetch_url_strips_html(monkeypatch):
    html = "<html><script>bad()</script><body><p>Hello <b>world</b></p></body></html>"
    monkeypatch.setattr(literature, "_get", lambda url, params=None: _FakeResponse(html))
    text = literature.fetch_url("http://example.org")
    assert "Hello" in text and "world" in text
    assert "bad()" not in text


def test_register_tools():
    from olivia.tools.registry import ToolRegistry

    registry = ToolRegistry()
    literature.register_tools(registry)
    assert set(registry.names()) == {"fetch_url", "literature_search"}
