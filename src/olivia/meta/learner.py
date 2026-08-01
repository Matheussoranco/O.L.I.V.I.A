"""MetaLearner — record every task outcome, learn which strategies win.

Inherited from I.S.A.A.C.: a small SQLite ledger of (task_kind, strategy,
success) rows whose Laplace-smoothed win-rates feed back into expert routing.
Connections are opened per operation so any thread may record safely.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    task_kind TEXT NOT NULL,
    strategy TEXT NOT NULL,
    success INTEGER NOT NULL,
    duration_s REAL NOT NULL DEFAULT 0,
    meta_json TEXT NOT NULL DEFAULT '{}'
)
"""


class MetaLearner:
    """Outcome ledger with win-rate queries."""

    def __init__(self, db_path: Path | None = None) -> None:
        from olivia.config import settings

        self.db_path = db_path or settings.data_dir() / "meta.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)
        conn.close()

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
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO outcomes (ts, task_kind, strategy, success, duration_s, meta_json)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    datetime.now().isoformat(timespec="seconds"),
                    task_kind,
                    strategy,
                    int(success),
                    duration_s,
                    json.dumps(meta or {}, default=str),
                ),
            )
        conn.close()

    def win_rate(self, task_kind: str, strategy: str, default: float = 0.5) -> float:
        """Laplace-smoothed ``(wins + 1) / (n + 2)``; ``default`` when unseen."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(success), 0) FROM outcomes"
                " WHERE task_kind = ? AND strategy = ?",
                (task_kind, strategy),
            ).fetchone()
        conn.close()
        n, wins = row
        if n == 0:
            return default
        return (wins + 1) / (n + 2)

    def rank_strategies(self, task_kind: str, strategies: list[str]) -> list[str]:
        """Stable sort of ``strategies`` by historical win-rate, best first."""
        return sorted(
            strategies,
            key=lambda s: self.win_rate(task_kind, s),
            reverse=True,
        )

    def stats(self) -> dict:
        """Totals per (task_kind, strategy) for introspection."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_kind, strategy, COUNT(*), COALESCE(SUM(success), 0)"
                " FROM outcomes GROUP BY task_kind, strategy"
            ).fetchall()
        conn.close()
        by_task: dict[str, dict] = {}
        total = 0
        for task_kind, strategy, n, wins in rows:
            total += n
            by_task.setdefault(task_kind, {})[strategy] = {
                "n": n,
                "wins": wins,
                "win_rate": (wins + 1) / (n + 2),
            }
        return {"total": total, "by_task": by_task}


_singleton: MetaLearner | None = None


def get_meta_learner() -> MetaLearner:
    """Process-level MetaLearner on the default database."""
    global _singleton
    if _singleton is None:
        _singleton = MetaLearner()
    return _singleton
