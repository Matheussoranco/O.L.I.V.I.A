# Evidence Pack — `O.L.I.V.I.A #24` (Guard Arithmetic & Non-Equation Symbolic Paths Against Explosive Powers)

- **Repository:** `Matheussoranco/O.L.I.V.I.A`
- **Issue:** `#24` (`Guard the arithmetic path of olivia solve against explosive powers (follow-up to #22)`)
- **PR:** `#27`
- **Trace:** `olivia-24`
- **Author:** Gemini 4 Neon (High reasoning effort)
- **Branch / Worktree:** `fix/24-arithmetic-power-guard` (`C:\Users\mathe\Documents\Code\O.L.I.V.I.A-wt24`, synced with `origin/main` @ `13cc792`)
- **Verification Status:** `PASS`
- **Review & Merge Readiness:** `READY_FOR_RE_REVIEW` (Round 3 fixes addressing Lead static re-review finding on structured/tuple/keyword arguments to eager operations + merged `origin/main`)

---

## 1. Root Cause & Implementation Summary (Round 3)

1. **Unified AST pre-evaluation guard inside `src/olivia/tools/science.py:safe_sympify()`:**
   - Operates directly on the **exact Python AST** produced by SymPy's `parse_expr` pipeline right before `compile()`/`eval()`, protecting both `olivia.study.solver` and `olivia.tools.science.symbolic_math` through one choke point.
   - **Round 3 (Lead static re-review finding — structured/tuple/keyword arguments):**
     - Added explicit AST node allowlist (`_ALLOWED_EXPR_NODES`) in `_check_expression()` and fail-closed default in `_ast_magnitude()` (rejects comprehensions, lambdas, subscripts, starred args, dicts/sets, and container/string arithmetic such as `([1] * 100000000)` or `('a' * 100000000)`).
     - Implemented per-operation argument-shape and bound validators in `_call_ast_magnitude()` — declining evaluation with `ExpressionLimitError` whenever an operation's work bound cannot be established:
       - `summation`, `product`, `Sum`, `Product`: requires 3-tuple `(symbol, lower, upper)` specs (accepting `ast.Tuple`, `ast.List`, or SymPy `Tuple(...)`) with finite numeric bounds and cumulative product-of-spans `<= 1000`; rejects symbolic/unbounded limits, invalid shapes, and kwargs.
       - `diff`, `Derivative`: validates `(symbol, order)` tuples, bare symbols, and numeric orders with cumulative derivative order `<= 16`; rejects symbolic/unbounded orders and kwargs.
       - `series`: validates positional order or `n=` kwarg `<= 32` (finite numeric) and allowlisted kwargs (`x`, `x0`, `n`, `dir`).
       - `integrate`, `Integral`: validates bare symbol or `(symbol, lower, upper)` 3-tuple with scalar bounded endpoints `<= 1000`; rejects kwargs and unexpected container shapes.
       - `limit`, `Limit`, `N`: validates scalar arguments, direction strings, and precision `<= 1000`.
       - `solve`, `linsolve`, `nonlinsolve`: allows scalar or 1D sequence of up to 16 scalar expressions under `child_limit = 64`; rejects nested containers and kwargs.
       - `Matrix`, `ImmutableMatrix`, `MatrixSymbol`, `eye`, `zeros`, `ones`, `diag`: validates 1D/2D shapes and finite numeric dimensions `<= 64`.
       - `_SCALAR_EAGER_CALLS` (`expand`, `factor`, `simplify`, `solveset`, `dsolve`, `nsolve`, etc.) & `_COMBINATORIAL_CALLS` (including `gamma`, `beta`, `binomial`, `rf`, `ff`, `factorial`, `fibonacci`, `factorint`, etc.): reject container arguments and kwargs, and enforce `<= 1000` on every numeric argument even when sibling arguments are symbolic (e.g. `binomial(100000, x)`, `rf(x, 100000)`).
     - Preserved Bandit `# nosec B307` annotation after merging `origin/main` (PR #26 + PR #28).
2. **Separated symbolic degree limits across operations (`src/olivia/study/solver.py` & `src/olivia/tools/science.py`):**
   - `safe_sympify(..., bound_symbolic_degree=False)` by default allows benign high-degree symbolic inputs (`differentiate x^100`, `derivative of x^1000`, `integrate x^100`, `simplify x^100/x^98`).
   - `expand` / `factor` pass `max_symbolic_degree=256`; `solve` / `find the roots of` pass `bound_symbolic_degree=True` (`<= 64`).
3. **Uniform stringification safety (`_safe_str` in `src/olivia/study/solver.py`):**
   - Wrapped `str(result)` across all symbolic branches so Python's `int_max_str_digits` (`ValueError`) always converts into a typed `SolverParseError`.
4. **Regression & subprocess timeout tests (`tests/test_study/test_solver_parse_errors.py`):**
   - Added 32 parametrized structured-argument / tuple / keyword / container-repetition / symbolic-bound refusal tests plus positive tests confirming bounded structured calls (`summation(i, (i, 1, 10))`, `diff(sin(x), (x, 2))`, `integrate(x**2, (x, 0, 1))`, `Matrix([[1, 2], [3, 4]])`, `series(sin(x), x, 0, 4)`) still succeed.

---

## 2. Commands Executed & Observed Results (Round 3)

| # | Check | Command | Exit Code | Observed Result |
|---|---|---|---|---|
| 1 | Ruff lint | `uv run --python 3.12 --extra dev --extra science ruff check src tests` | `0` | `All checks passed!` |
| 2 | Ruff format | `uv run --python 3.12 --extra dev --extra science ruff format --check src tests` | `0` | `90 files already formatted` |
| 3 | Mypy type check | `uv run --python 3.12 --extra dev --extra science mypy src/olivia` | `0` | `Success: no issues found in 65 source files` |
| 4 | Full test suite | `uv run --python 3.12 --extra dev --extra science pytest tests/ -q` | `0` | `425 passed, 2 skipped` |
| 5 | Offline eval gate | `uv run --python 3.12 --extra dev --extra science olivia eval --check` | `0` | `All gates hold.` |

---

## 3. Acceptance Criteria Traceability (`#24`)

- [x] `calculate 9^9^9 * 2` and `what is 2^999999999 + 1` return in `< 2 s` with `method="none"` and log a typed `SolverParseError` warning.
- [x] Direct `olivia.tools.science.symbolic_math` calls are protected at the same `safe_sympify()` AST choke point.
- [x] Benign non-solve large-exponent symbolic expressions (`differentiate x^100`, `integrate x^100`, `expand (x+1)^100`, `factor x^100 - 1`) continue to succeed.
- [x] `what is 2^10 + 1` still answers `1025`.
- [x] `olivia eval --check` holds (`All gates hold.`).
- [x] No external downloads, no direct merge to `main`.
