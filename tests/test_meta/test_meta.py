"""MetaLearner — SQLite outcome ledger with Laplace-smoothed win-rates."""

from __future__ import annotations

from olivia.meta import MetaLearner, get_meta_learner


def test_win_rate_laplace_smoothing():
    learner = MetaLearner()
    learner.record("ask", "math", True)
    learner.record("ask", "math", True)
    learner.record("ask", "math", False)
    assert learner.win_rate("ask", "math") == (2 + 1) / (3 + 2)  # 0.6


def test_win_rate_unseen_uses_default():
    learner = MetaLearner()
    assert learner.win_rate("ask", "never-used") == 0.5
    assert learner.win_rate("ask", "never-used", default=0.9) == 0.9


def test_rank_strategies_orders_by_history():
    learner = MetaLearner()
    for _ in range(4):
        learner.record("ask", "winner", True)
    for _ in range(4):
        learner.record("ask", "loser", False)
    ranked = learner.rank_strategies("ask", ["loser", "unseen", "winner"])
    assert ranked == ["winner", "unseen", "loser"]  # unseen 0.5 sits between


def test_stats_aggregates_per_task_and_strategy():
    learner = MetaLearner()
    learner.record("ask", "math", True, duration_s=0.1, meta={"q": "x"})
    learner.record("research", "cycle:research", False)
    stats = learner.stats()
    assert stats["total"] == 2
    assert stats["by_task"]["ask"]["math"]["wins"] == 1
    assert stats["by_task"]["research"]["cycle:research"]["n"] == 1


def test_persistence_across_instances():
    MetaLearner().record("ask", "math", True)
    assert MetaLearner().win_rate("ask", "math") == (1 + 1) / (1 + 2)  # same isolated db


def test_get_meta_learner_is_a_singleton():
    assert get_meta_learner() is get_meta_learner()
