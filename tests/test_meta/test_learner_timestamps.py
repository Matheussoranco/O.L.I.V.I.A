"""MetaLearner records timezone-aware (UTC) timestamps."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from olivia.meta import MetaLearner


def test_recorded_timestamps_are_utc_aware(tmp_path):
    learner = MetaLearner(db_path=tmp_path / "meta.db")
    learner.record("ask", "math", True)

    with sqlite3.connect(tmp_path / "meta.db") as conn:
        (ts,) = conn.execute("SELECT ts FROM outcomes").fetchone()
    assert datetime.fromisoformat(ts).tzinfo is not None  # naive would fail here
    assert learner.win_rate("ask", "math") == (1 + 1) / (1 + 2)  # ledger still works
