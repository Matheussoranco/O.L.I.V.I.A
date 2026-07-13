"""Lab notebook — append-only JSON log with keyword search."""

from __future__ import annotations

from olivia.memory import Notebook


def test_add_persists_and_reloads():
    notebook = Notebook()
    entry = notebook.add("finding", "Spacing beats massing.", tags=["srs"], meta={"cycle": 1})
    assert entry["id"].startswith("note_")
    assert entry["kind"] == "finding"

    reloaded = Notebook()  # same isolated default path
    assert len(reloaded.entries()) == 1
    assert reloaded.entries()[0]["content"] == "Spacing beats massing."
    assert reloaded.entries()[0]["meta"] == {"cycle": 1}


def test_entries_filters_by_kind():
    notebook = Notebook()
    notebook.add("finding", "a")
    notebook.add("note", "b")
    assert len(notebook.entries()) == 2
    assert [e["content"] for e in notebook.entries("note")] == ["b"]


def test_search_scores_keywords():
    notebook = Notebook()
    notebook.add("note", "gravity bends light")
    notebook.add("note", "light light light everywhere")
    notebook.add("note", "unrelated entry")

    hits = notebook.search("light")
    assert len(hits) == 2
    assert hits[0]["content"] == "light light light everywhere"  # highest term count first


def test_search_requires_all_wanted_tags():
    notebook = Notebook()
    notebook.add("note", "tagged both", tags=["physics", "Optics"])
    notebook.add("note", "tagged one", tags=["physics"])

    hits = notebook.search(tags=["physics", "optics"])  # tag match is casefolded
    assert [h["content"] for h in hits] == ["tagged both"]


def test_search_empty_query_ranks_by_recency_and_limits():
    notebook = Notebook()
    for i in range(5):
        notebook.add("note", f"entry {i}")
    hits = notebook.search(limit=3)
    assert len(hits) == 3


def test_search_no_match_returns_empty():
    notebook = Notebook()
    notebook.add("note", "alpha beta")
    assert notebook.search("gamma") == []


def test_corrupt_notebook_starts_empty(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("[{not json", encoding="utf-8")
    notebook = Notebook(path=path)
    assert notebook.entries() == []
    notebook.add("note", "fresh start")  # and it can write over the corruption
    assert len(Notebook(path=path).entries()) == 1
