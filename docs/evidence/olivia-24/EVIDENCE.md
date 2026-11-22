# Evidence Pack — `O.L.I.V.I.A #24` (Guard Arithmetic & Non-Equation Symbolic Paths Against Explosive Powers)

- **Repository:** `Matheussoranco/O.L.I.V.I.A`
- **Issue:** `#24` (`Guard the arithmetic path of olivia solve against explosive powers (follow-up to #22)`)
- **PR:** `#27`
- **Trace:** `olivia-24`
- **Author:** Gemini 4 Neon (High reasoning effort)
- **Branch / Worktree:** `fix/24-arithmetic-power-guard` (`C:\Users\mathe\Documents\Code\O.L.I.V.I.A-wt24`, base `origin/main` @ `c1d797c`)
- **Verification Status:** `PASS`
- **Review & Merge Readiness:** `READY_FOR_RE_REVIEW` (Round 2 fixes addressing Lead & Claude findings on unified `safe_sympify` AST guarding, non-solve large-exponent support, eager-op guards, and `_safe_str` formatting bounds)

---

## 1. Root Cause & Implementation Summary (Round 2)

1. **Unified AST pre-evaluation guard inside `src/olivia/tools/science.py:safe_sympify()`:**
   - Moved the magnitude, power, combinatorial, and eager-operation guard (`_ast_magnitude`, `_call_ast_magnitude`, `_check_power_bounds`, `ExpressionLimitError`) directly into `safe_sympify()` operating on the **exact Python AST** produced by SymPy's `parse_expr` pipeline right before `compile()`/`eval()`.
   - Eliminates parser-divergence between pre-checks and evaluation, covers both `olivia.study.solver` and `olivia.tools.science.symbolic_math` through one choke point, and catches eager Python/SymPy operations including integer powers (`**`), bit-shifts (`<<`/`>>`), `pow(a, b)`, `factorial`/`gamma`/`binomial`/`rf`/`ff`/`risingfactorial`/`fallingfactorial`/`fibonacci`/`lucas`/`bell`, and nested power towers.
   - Note on scope: this is a bounded structural pre-evaluation guard on parsed expressions, not a formal proof against arbitrary symbolic blowup; SymPy can still produce large symbolic expressions from valid inputs, which are further guarded at stringification via `_safe_str`.
2. **Separated symbolic degree limits across operations (`src/olivia/study/solver.py` & `src/olivia/tools/science.py`):**
   - `safe_sympify(..., bound_symbolic_degree=False)` by default allows benign high-degree symbolic inputs (`differentiate x^100`, `derivative of x^1000`, `integrate x^100`, `simplify x^100/x^98`) while still rejecting explosive integer powers and eager calls.
   - `expand` / `factor` pass `max_symbolic_degree=256` (`expand (x+1)^100` and `factor x^100 - 1` succeed; `expand (x+1)^100000` is refused fast).
   - `solve` / `find the roots of` pass `bound_symbolic_degree=True` (`<= 64`) to keep polynomial root-finding tractable.
3. **Uniform stringification safety (`_safe_str` in `src/olivia/study/solver.py`):**
   - Wrapped `str(result)` across all symbolic branches (`diff`, `integrate`, `f'(x)`, `find roots`, `limit`, `simplify`, `factor`, `expand`, `_evaluate_arithmetic`) so Python's `int_max_str_digits` (`ValueError`) always converts into a typed `SolverParseError` rather than leaking unhandled exceptions.
4. **Public helper retained (`src/olivia/study/equations.py`):**
   - `check_expression_growth(expression: str)` remains available for equation callers; note `isinstance(x, int | float | str)` normalization is also present in `equations.py` to satisfy both Ruff `v0.1.5` and `v0.15.2`.
5. **Regression & subprocess timeout tests (`tests/test_study/test_solver_parse_errors.py`):**
   - 13 explosive/eager-op/bitshift/power-tower inputs refused fast (`< 2.0s` each) in timeout-isolated subprocesses across both `olivia.study.solver` and `olivia.tools.science.symbolic_math`.
   - 6 non-solve large-exponent positive tests (`differentiate x^100`, `derivative of x^1000`, `integrate x^100`, `simplify x^100/x^98`, `expand (x+1)^100`, `factor x^100 - 1`) plus bounded arithmetic power evaluations (`2^10 + 1`, `2^(3^2) + 1`, `2**10 - 24`).

---

## 2. Commands Executed & Observed Results (Round 2)

| # | Check | Command | Exit Code | Observed Result |
|---|---|---|---|---|
| 1 | Ruff lint | `.venv\Scripts\ruff.exe check src tests` | `0` | `All checks passed!` |
| 2 | Ruff format | `.venv\Scripts\ruff.exe format --check src tests` | `0` | `90 files already formatted` |
| 3 | Mypy type check | `.venv\Scripts\mypy.exe src/olivia` | `0` | `Success: no issues found in 65 source files` |
| 4 | Full test suite | `PYTHONPATH=src .venv\Scripts\python.exe -m pytest tests/ -q --tb=short` | `0` | `390 passed, 2 skipped` |
| 5 | Offline eval gate | `PYTHONPATH=src .venv\Scripts\python.exe -m olivia eval --check` | `0` | `All gates hold.` |

---

## 3. Acceptance Criteria Traceability (`#24`)

- [x] `calculate 9^9^9 * 2` and `what is 2^999999999 + 1` return in `< 2 s` with `method="none"` and log a typed `SolverParseError` warning.
- [x] Direct `olivia.tools.science.symbolic_math` calls are protected at the same `safe_sympify()` AST choke point.
- [x] Benign non-solve large-exponent symbolic expressions (`differentiate x^100`, `integrate x^100`, `expand (x+1)^100`, `factor x^100 - 1`) continue to succeed.
- [x] `what is 2^10 + 1` still answers `1025`.
- [x] `olivia eval --check` holds (`All gates hold.`).
- [x] No external downloads, no direct merge to `main`.
