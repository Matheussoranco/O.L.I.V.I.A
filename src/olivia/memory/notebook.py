"""Lab notebook — an append-only JSON log of findings, notes, and progress.

Deliberately boring: plain JSON, keyword search, no embeddings.  The notebook
is the agent's provenance trail (what was found, when, in which cycle), so it
must stay readable by a human with a text editor.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from olivia.core.records import new_id
from olivia.core.storage import atomic_write_json, quarantine_corrupt_file

logger = logging.getLogger(__name__)


class Notebook:
    """Append-only entries: ``{id, ts, kind, content, tags, meta}``."""

    def __init__(self, path: Path | None = None) -> None:
        from olivia.config import settings

        self.path = path or settings.data_dir() / "notebook.json"
        self._entries: list[dict] = []
        self._load_failed = False
        if self.path.exists():
            try:
                self._entries = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(self._entries, list) or not all(
                    isinstance(entry, dict) for entry in self._entries
                ):
                    raise ValueError("notebook root must be a list of objects")
            except Exception as exc:
                self._load_failed = True
                logger.warning("Could not load notebook %s: %s", self.path, exc)

    def add(
        self,
        kind: str,
        content: str,
        tags: list[str] | None = None,
        meta: dict | None = None,
    ) -> dict:
        """Append one entry and persist immediately."""
        entry = {
            "id": new_id("note"),
            "ts": datetime.now().isoformat(timespec="seconds"),
            "kind": kind,
            "content": content,
            "tags": tags or [],
            "meta": meta or {},
        }
        self._entries.append(entry)
        self.save()
        return entry

    def entries(self, kind: str | None = None) -> list[dict]:
        return [e for e in self._entries if kind is None or e.get("kind") == kind]

    def search(
        self,
        query: str = "",
        kind: str | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Keyword-scored search; empty query ranks by recency alone."""
        wanted_tags = {t.casefold() for t in (tags or [])}
        terms = [t for t in query.casefold().split() if t]

        candidates = []
        for entry in self._entries:
            if kind is not None and entry.get("kind") != kind:
                continue
            entry_tags = {str(t).casefold() for t in entry.get("tags", [])}
            if wanted_tags and not wanted_tags <= entry_tags:
                continue
            haystack = entry.get("content", "").casefold() + " " + " ".join(entry_tags)
            score = sum(haystack.count(term) for term in terms)
            if terms and score == 0:
                continue
            candidates.append((score, entry.get("ts", ""), entry))

        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [entry for _, _, entry in candidates[:limit]]

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._load_failed:
            backup = quarantine_corrupt_file(self.path)
            if backup:
                logger.warning("Preserved corrupt notebook as %s", backup)
            self._load_failed = False
        atomic_write_json(self.path, self._entries)
        return self.path
