"""MetaLearner — record labelled task outcomes, learn which strategies win.

Inherited from I.S.A.A.C.: a small SQLite ledger of (task_kind, strategy,
success) rows whose Laplace-smoothed win-rates feed back into expert routing.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    task_kind TEXT NOT NULL,
    strategy TEXT NOT NULL,
    success INTEGER NOT NULL,
    duration_s REAL DEFAULT 0.0,
    meta_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_outcomes_lookup
ON outcomes (task_kind, strategy);
"""


class MetaLearner:
    """Outcome ledger with win-rate queries.

    Routing consumers should only query buckets whose rows have an external
    correctness label. Self-reported confidence belongs in a separate bucket.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        from olivia.config import settings

        self.db_path = db_path or settings.data_dir() / "meta.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # `with conn` commits on clean exit and rolls back on error; no
        # explicit close() needed — leaving the block closes the connection.
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10.0)

    def record(
        self,
        task_kind: str,
        strategy: str,
        success: bool,
        duration_s: float = 0.0,
        meta: dict | None = None,
    ) -> None:
        """Persist a single outcome into the ledger."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO outcomes (ts, task_kind, strategy, success, duration_s, meta_json)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    task_kind,
                    strategy,
                    int(success),
                    float(duration_s),
                    json.dumps(meta or {}, default=str),
                ),
            )
        # `with` commits on success / rolls back on error and closes the
        # connection — no explicit close() here.

    #: Pessimistic prior for never-seen strategies when explicitly requested.
    UNSEEN_PRIOR: float = 0.3

    def win_rate(self, task_kind: str, strategy: str, default: float = 0.5) -> float:
        """Laplace-smoothed ``(wins + 1) / (n + 2)``; ``default`` when unseen."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(success), 0) FROM outcomes"
                " WHERE task_kind = ? AND strategy = ?",
                (task_kind, strategy),
            ).fetchone()
        n, wins = row
        if n == 0:
            return default
        return (wins + 1.0) / (n + 2.0)

    def rank_strategies(
        self,
        task_kind: str,
        candidates: list[str],
        default: float = 0.5,
    ) -> list[str]:
        """Sort ``candidates`` by historical win-rate descending, ties preserved."""
        scores = {strat: self.win_rate(task_kind, strat, default=default) for strat in candidates}
        return sorted(candidates, key=lambda s: scores[s], reverse=True)

    def stats(self) -> dict:
        """Aggregate summary per (task_kind, strategy)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_kind, strategy, COUNT(*), COALESCE(SUM(success), 0)"
                " FROM outcomes GROUP BY task_kind, strategy"
            ).fetchall()
        by_task: dict[str, dict] = {}
        total = 0
        for task_kind, strategy, n, wins in rows:
            by_task.setdefault(task_kind, {})[strategy] = {
                "n": n,
                "wins": wins,
                "win_rate": round((wins + 1.0) / (n + 2.0), 3),
            }
            total += n
        return {"total": total, "by_task": by_task}


_singleton: MetaLearner | None = None


def get_meta_learner() -> MetaLearner:
    """Process-wide MetaLearner singleton."""
    global _singleton
    if _singleton is None:
        _singleton = MetaLearner()
    return _singleton
