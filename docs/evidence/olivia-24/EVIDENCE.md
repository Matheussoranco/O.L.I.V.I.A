# Evidence Pack — `O.L.I.V.I.A #24` (Guard Arithmetic & Non-Equation Symbolic Paths Against Explosive Powers)

- **Repository:** `Matheussoranco/O.L.I.V.I.A`
- **Issue:** `#24` (`Guard the arithmetic path of olivia solve against explosive powers (follow-up to #22)`)
- **Trace:** `olivia-24`
- **Author:** Gemini 4 Neon (High reasoning effort, session `7f54c219-94aa-4eee-be8a-2152f9236c40`)
- **Branch / Worktree:** `fix/24-arithmetic-power-guard` (`C:\Users\mathe\Documents\Code\O.L.I.V.I.A-wt24`, base `origin/main` @ `c1d797c`)
- **Verification Status:** `PASS`
- **Review & Merge Readiness:** `PENDING_REVIEW` (awaiting independent cross-agent review from Claude Code and final integration assessment from Engineering Lead)

---

## 1. Root Cause & Implementation Summary

1. **Public structural pre-evaluation growth guard (`src/olivia/study/equations.py`):**
   - Promoted `check_expression_growth(expression: str) -> None` as a public wrapper around `_check_growth(...)`, translating `_TooLarge` into a typed `SolverParseError` carrying the offending `expression`.
   - Reuses the exact AST-level magnitude analysis introduced in PR #22 (`MAX_RESULT_DIGITS = 1000`, `MAX_EXPONENT = 64`, `MAX_COMBINATORIAL_ARGUMENT = 1000`) before SymPy parses or evaluates `Integer ** Integer` eagerly.
2. **Unified guard across arithmetic & non-equation math branches (`src/olivia/study/solver.py`):**
   - Called `check_expression_growth(text)` inside `olivia.study.solver._sympify(text)` prior to `safe_sympify(text, implicit_multiplication=True)`.
   - Protects `_evaluate_arithmetic` (`calculate 9^9^9 * 2`, `what is 2^999999999 + 1`, `what is 2^(((999999999))) + 1`, `what is 2^2^2^2^2 + 1`, `calculate 2**999999999`) as well as non-equation symbolic branches (`differentiate`, `integrate`, `If f(x) = ...`, `find the roots of ...`, `limit`, `simplify`, `factor`, `expand`).
   - Added defense-in-depth `ValueError` (`"integer string conversion"`) handling around `sympy.N(expr)` / stringification in `_evaluate_arithmetic` so products of individually bounded large integers (`(10^500)^9` → 4500 digits) also raise typed `SolverParseError` rather than leaking a bare `ValueError`.
   - Zero overlap with Hermes's active `olivia-17-t9` PR #26 (`literature.py`, `worksheet.py`, `science.py`, `pyproject.toml`, `uv.lock`).
3. **Timeout-isolated & functional regression tests (`tests/test_study/test_solver_parse_errors.py`):**
   - `test_explosive_arithmetic_and_symbolic_paths_refused_fast`: runs 9 explosive inputs (including `calculate 9^9^9 * 2`, `what is 2^999999999 + 1`, nested parens, power towers, `**`, 4500-digit product, `simplify`, `differentiate`, `find the roots of`) in a timeout-isolated subprocess, asserting `_solve_math` raises `SolverParseError`, `solve_problem(..., NullClient())` returns `method="none"`, and every case completes in `< 2.0s`.
   - `test_bounded_arithmetic_powers_still_evaluate`: verifies `what is 2^10 + 1` → `"1025"`, `calculate 2^(3^2) + 1` → `"513"`, `what is 2**10 - 24` → `"1000"`.
   - `test_explosive_arithmetic_logs_warning_and_abstains`: verifies `WARNING` log on `olivia.study.solver` and honest offline abstention (`method="none"`, `confidence=0.0`).
   - `test_check_expression_growth_rejects_explosive_power_and_allows_bounded`: direct unit test of the promoted public helper.

---

## 2. Commands Executed & Observed Results

| # | Check | Command | Exit Code | Observed Result |
|---|---|---|---|---|
| 1 | Ruff lint | `.venv\Scripts\ruff.exe check src tests` | `0` | `All checks passed!` |
| 2 | Ruff format | `.venv\Scripts\ruff.exe format --check src tests` | `0` | `90 files already formatted` |
| 3 | Full test suite | `PYTHONPATH=src .venv\Scripts\python.exe -m pytest tests/ -q --tb=short` | `0` | `383 passed, 2 skipped in 26.28s` |
| 4 | Offline eval gate | `PYTHONPATH=src .venv\Scripts\python.exe -m olivia eval --check` | `0` | `All gates hold.` (research 100%, study 100%, symbolic 78.1% accuracy / 100% precision / 0% wrong rate) |

---

## 3. Acceptance Criteria Traceability (`#24`)

- [x] `calculate 9^9^9 * 2` and `what is 2^999999999 + 1` return in `< 2 s` with `method="none"` and log a typed `SolverParseError` warning (`test_explosive_arithmetic_and_symbolic_paths_refused_fast`, `test_explosive_arithmetic_logs_warning_and_abstains`).
- [x] `what is 2^10 + 1` still answers `1025` (`test_bounded_arithmetic_powers_still_evaluate`).
- [x] `olivia eval --check` holds (`All gates hold.`).
- [x] No external downloads, no direct merge to `main`, zero file overlap with `olivia-17-t9` PR #26.

---

## 4. Limitations & Follow-Ups

- `olivia.tools.science.safe_sympify` itself was intentionally left untouched in this PR to maintain zero file overlap with `olivia-17-t9` (PR #26). After PR #26 merges, callers of `symbolic_math` outside `study/` could optionally invoke `check_expression_growth` as well if desired.
