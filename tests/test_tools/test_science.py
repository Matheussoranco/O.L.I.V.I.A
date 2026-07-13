"""Science tools — sandbox execution and stdlib statistics."""

from __future__ import annotations

from olivia.tools import science


def test_python_exec_ok():
    out = science.python_exec("print(2 + 2)")
    assert out["ok"] and out["stdout"].strip() == "4"


def test_python_exec_error():
    out = science.python_exec("raise ValueError('boom')")
    assert not out["ok"] and "boom" in out["stderr"]


def test_python_exec_timeout():
    out = science.python_exec("while True: pass", timeout=1.0)
    assert not out["ok"] and "timeout" in out["stderr"]


def test_symbolic_math_or_honest_error():
    result = science.symbolic_math("(x**2 - 4)", "solve")
    try:
        import sympy  # noqa: F401

        assert "2" in result and not result.startswith("error:")
    except ImportError:
        assert result.startswith("error: sympy not installed")


def test_symbolic_math_rejects_unknown_operation():
    assert science.symbolic_math("x", "hack").startswith("error: unknown operation")


def test_stats_summary():
    summary = science.stats_summary([1.0, 2.0, 3.0, 4.0])
    assert summary["n"] == 4 and summary["mean"] == 2.5 and "stdev" in summary
    assert science.stats_summary([]) == {"n": 0}


def test_welch_ttest_separated_vs_identical():
    a = [10.0, 11.0, 9.5, 10.5, 10.2, 9.8]
    b = [2.0, 2.5, 1.8, 2.2, 2.1, 1.9]
    separated = science.welch_ttest(a, b)
    assert separated["p_value"] < 0.001 and separated["cohens_d"] > 2

    identical = science.welch_ttest(a, list(a))
    assert identical["p_value"] > 0.9 and abs(identical["t"]) < 1e-9


def test_required_sample_size_known_value():
    # d = 0.5, alpha .05, power .8 → n ≈ 63 per group (normal approximation)
    assert science.required_sample_size(0.5) == 63
    assert science.required_sample_size(0) == 0


def test_register_tools():
    from olivia.tools.registry import ToolRegistry

    registry = ToolRegistry()
    science.register_tools(registry)
    assert {"python_exec", "symbolic_math", "stats_test", "sample_size"} <= set(registry.names())
