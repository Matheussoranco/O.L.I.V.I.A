"""Symbolic-solving accuracy — the symbolic-first path and the LLM fallback,
measured separately.

Why separately: ``solve_problem`` tries every deterministic solver and only
then asks a model.  If the two were scored together, a regression in the
symbolic path would be masked by the model quietly picking up the slack — the
exact failure this harness exists to prevent.  So:

* the **symbolic** pass runs with :class:`~olivia.llm.client.NullClient`, which
  makes the fallback unreachable by construction;
* the **fallback** pass then runs *only* the cases the symbolic pass abstained
  on — the real fallback population — and is reported under its own metric
  names, never merged into the symbolic ones.

Every case ends as ``correct``, ``wrong`` (an answer was produced and it is
not right — the dangerous outcome) or ``abstain`` (``method == "none"``).
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any

from olivia.core.records import WorkedSolution
from olivia.eval.harness import (
    CaseResult,
    Metric,
    SuiteReport,
    accuracy_metrics,
    group_accuracy,
    load_dataset,
    ratio,
    register_suite,
    tally,
)
from olivia.llm.client import LLMClient, NullClient

_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
_FRACTION_RE = re.compile(r"^\s*([-+]?\d+)\s*/\s*(\d+)\s*$")
_ROOT_RE = re.compile(r"=\s*([^,]+)")


# ---------------------------------------------------------------------------
# Answer checking
# ---------------------------------------------------------------------------


def _first_number(text: str) -> float | None:
    """Leading numeric value of an answer string ('98.08 g/mol' -> 98.08)."""
    fraction = _FRACTION_RE.match(text)
    if fraction:
        return float(Fraction(int(fraction.group(1)), int(fraction.group(2))))
    match = _NUMBER_RE.search(text)
    return float(match.group()) if match else None


def _sympy():
    try:
        import sympy
    except ImportError:  # pragma: no cover - science extra absent
        return None
    return sympy


def _math_equal(got: str, expected: str) -> bool:
    """Symbolic equality, tolerant of ``+ C`` and formatting differences."""
    sympy = _sympy()
    if sympy is None:
        return got.replace(" ", "") == expected.replace(" ", "")
    cleaned = re.sub(r"\+\s*C\s*$", "", got).strip()
    try:
        difference = sympy.simplify(sympy.sympify(cleaned) - sympy.sympify(expected))
        return bool(difference == 0)
    except Exception:
        return False


def _roots_equal(got: str, expected: list[str]) -> bool:
    """Compare a 'x = 2, x = 3' answer with an expected root set."""
    found = [part.strip() for part in _ROOT_RE.findall(got)]
    if len(found) != len(expected):
        return False
    sympy = _sympy()
    if sympy is None:
        return sorted(found) == sorted(expected)
    try:
        got_set = {sympy.nsimplify(sympy.sympify(v)) for v in found}
        want_set = {sympy.nsimplify(sympy.sympify(v)) for v in expected}
    except Exception:
        return False
    return got_set == want_set


def check_answer(check: dict[str, Any], answer: str) -> bool:
    """Score one produced answer against its expectation."""
    if not answer.strip():
        return False
    kind = check.get("kind")
    if kind == "numeric":
        value = _first_number(answer)
        if value is None:
            return False
        target = float(check["value"])
        rtol = float(check.get("rtol", 1e-6))
        return abs(value - target) <= rtol * max(abs(target), 1e-12)
    if kind == "contains":
        low = answer.casefold()
        return all(str(v).casefold() in low for v in check["values"])
    if kind == "math_equal":
        return _math_equal(answer, str(check["expr"]))
    if kind == "roots":
        return _roots_equal(answer, [str(v) for v in check["values"]])
    raise ValueError(f"unknown check kind: {kind!r}")


def _score(case: dict[str, Any], solution: WorkedSolution) -> CaseResult:
    expected = str(case["check"].get("value", case["check"].get("expr", "")))
    if not expected:
        expected = ", ".join(str(v) for v in case["check"].get("values", []))
    result = CaseResult(
        id=case["id"],
        group=f"{case['tier']}.{case['domain']}",
        expected=expected,
        got=solution.final_answer,
        meta={
            "domain": case["domain"],
            "tier": case["tier"],
            "method": solution.method,
            "confidence": solution.confidence,
            "problem": case["problem"],
        },
    )
    if solution.method == "none":
        result.outcome = "abstain"
        result.detail = "no solver matched and no fallback available"
    elif check_answer(case["check"], solution.final_answer):
        result.outcome = "correct"
    else:
        result.outcome = "wrong"
    return result


# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


def _method_counts(cases: list[CaseResult]) -> list[Metric]:
    total = len(cases)
    counts: dict[str, int] = {}
    for case in cases:
        counts[case.meta.get("method", "?")] = counts.get(case.meta.get("method", "?"), 0) + 1
    return [
        Metric(f"routed_to.{method}", ratio(count, total), total)
        for method, count in sorted(counts.items())
    ]


def run(client: LLMClient | None = None) -> SuiteReport:
    """Score the symbolic path, then the fallback path on what it abstained on."""
    from olivia.study.solver import solve_problem

    data = load_dataset("symbolic_solving")
    cases: list[dict[str, Any]] = data["cases"]
    report = SuiteReport(suite="symbolic")

    # --- pass 1: symbolic only (NullClient makes the LLM branch unreachable)
    symbolic_results: list[CaseResult] = []
    for case in cases:
        solution = solve_problem(case["problem"], client=NullClient())
        symbolic_results.append(_score(case, solution))
    report.cases = symbolic_results
    report.metrics = accuracy_metrics(symbolic_results, prefix="symbolic.")
    report.metrics += group_accuracy(symbolic_results, prefix="symbolic.")
    report.metrics += _method_counts(symbolic_results)

    coverage = ratio(
        sum(1 for c in symbolic_results if c.meta.get("method") != "none"), len(symbolic_results)
    )
    report.metrics.append(
        Metric("symbolic.coverage", coverage, len(symbolic_results), "cases a solver claimed")
    )

    # --- pass 2: the fallback, on the cases the symbolic path could not touch
    abstained = [c for c in symbolic_results if c.outcome == "abstain"]
    if client is None or not client.available:
        report.notes.append(
            f"fallback path not measured: no LLM backend configured "
            f"({len(abstained)} cases would have been routed to it)"
        )
        report.metrics.append(
            Metric("fallback.measured", 0.0, len(abstained), "no LLM backend — see notes")
        )
        return report

    by_id = {case["id"]: case for case in cases}
    fallback_results: list[CaseResult] = []
    for stub in abstained:
        case = by_id[stub.id]
        solution = solve_problem(case["problem"], client=client)
        scored = _score(case, solution)
        scored.group = f"fallback.{case['domain']}"
        fallback_results.append(scored)
    report.cases += fallback_results
    report.metrics += accuracy_metrics(fallback_results, prefix="fallback.")
    report.metrics.append(Metric("fallback.measured", 1.0, len(fallback_results), "cases routed"))
    report.notes.append(
        f"fallback recovered {tally(fallback_results, 'correct')}/{len(fallback_results)} "
        "of the cases the symbolic path abstained on"
    )
    return report


register_suite("symbolic", run)
