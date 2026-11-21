# Evidence Pack — O.L.I.V.I.A. #12 (T4: Equation Parser — Systems + Notation Variants)

| Field | Value |
|---|---|
| Ticket | [#12](https://github.com/Matheussoranco/O.L.I.V.I.A/issues/12) (child of spec #8) |
| Trace id | `olivia-12-t4` |
| Author | Claude Code, Opus 5.5 (session `b4efa619`) |
| Base | `origin/main` @ `3295f408fedeca09724175ca37b2df8d1f3374d9` |
| Revision verified | `37c184b84688160cc8156153e73f6bef8b6c8e09` (branch `feat/12-equation-parser-systems`) |
| Independent reviewer | **Pending**: Gemini 4 Neon (requested). Engineering Lead (Codex) does the integration assessment. |
| Status | Implementation complete, gates pass. **Not reviewed yet.** A passing test run is not review approval. |

Logs in `logs/` were produced by the commands shown at their top, on the revision
above. Local absolute paths were redacted to `<worktree>` / `~`.

## 1. Scope → proof

| Acceptance criterion (#12) | Proof | Result |
|---|---|---|
| `olivia solve "the system 2x + y = 10 and x - y = 2"` → `x = 4, y = 2` with worked steps | `test_acceptance_via_olivia_solve_cli[the system…]` (runs the real Typer CLI), `test_acceptance_system_shows_worked_steps`; `logs/07-probe-head.txt` | PASS (failed on `origin/main`: `logs/06`) |
| `olivia solve "solve 2x + y = 10, x - y = 2"` | CLI test; probe | PASS (already passed on main) |
| `olivia solve "x^2 - 5x + 6 = 0"` | CLI test; probe | PASS (already passed on main) |
| `olivia solve "2*x + 3 = 7"` | CLI test; probe | PASS (already passed on main) |
| All existing solver tests still pass | `logs/03-pytest-full.txt`: 365 passed, 2 skipped. Baseline on `3295f40` was 263 passed, 2 skipped; the +102 are the new tests. **No existing test was edited.** | PASS |

The baseline run on `origin/main` found three of the four criteria already met
by PR #19. The remaining one, the headline case, is why the work went past a
regex tweak: see §3.

## 2. Verification commands (all on `37c184b`)

| # | Command | Result | Log |
|---|---|---|---|
| 0 | `python -c "import olivia; print(olivia.__file__)"` with `PYTHONPATH=<worktree>/src` | imports the worktree, not the main checkout | `logs/00-import-path.txt` |
| 1 | `ruff check src/ tests/` + `ruff format --check src/ tests/` (ruff 0.15.2, the CI pin) | exit 0 / exit 0 | `logs/01-ruff.txt` |
| 2 | `mypy 1.13.0` on `study/equations.py` + `study/solver.py` | `Success: no issues found in 2 source files` | `logs/02-mypy.txt` |
| 3 | `pytest tests/ -q` | 365 passed, 2 skipped | `logs/03-pytest-full.txt` |
| 4 | `pytest tests/test_study/test_equations.py -v` | 102 passed | `logs/04-pytest-equations-verbose.txt` |
| 5 | `olivia eval --check` | `All gates hold.` exit 0 | `logs/05-eval-check.txt` |
| 6 | `probe.py` on `origin/main` (via `git archive`) | see table below | `logs/06-probe-origin-main.txt` |
| 7 | `probe.py` on HEAD | see table below | `logs/07-probe-head.txt` |

**Eval gate, before vs after.** I compared the JSON outputs of `olivia eval
--check --json` on `3295f40` and on the implementation: **0 of 46 metrics
changed**. `symbolic.accuracy` stays at 78.1% and `symbolic.wrong_rate` at 0.0%.
This ticket was not meant to move the held-out score (that's T3, #11), and it
doesn't.

**Integration with PR #20 (T8, Gemini).** I trial-merged `origin/fix/16-mypy-real-errors`
@ `6947c35` onto this branch in a throwaway worktree, which I then removed.

- `solver.py` conflicts. #20 annotates `steps` in the system branch that #12
  deletes, so the resolution is to take #12's side.
- On the merged tree: `mypy src/olivia` with the project venv gives `Success: no
  issues found in 65 source files`, and `pytest` gives 367 passed, 2 skipped.
- Counterfactual, the same merge without commit `37c184b`: mypy fails with
  `solver.py:190: Need type annotation for "steps"`. That commit is what keeps
  #20's new CI mypy gate green.

These merged-tree runs were done by hand. Their output is quoted here and is
not in `logs/`.

## 3. Observed behaviour: `origin/main` vs this branch

The text below is from `logs/06` and `logs/07`, run offline with `NullClient`.

| Problem | `origin/main` | This branch |
|---|---|---|
| `the system 2x + y = 10 and x - y = 2` | unsolved | `x = 4, y = 2` |
| `solve 2x + y = 10; x - y = 2` | unsolved | `x = 4, y = 2` |
| `solve for x and y: 2x + y = 10, x - y = 2` | unsolved | `x = 4, y = 2` |
| `solve x + y + z = 6, 2x - y + z = 3, x + 2y - z = 2` | unsolved | `x = 1, y = 2, z = 3` |
| `x² − 5x + 6 = 0` / `2×x + 3 = 7` | unsolved | `x = 2, x = 3` / `x = 2` |
| `solve x1 + x2 = 3 and x1 - x2 = 1` | unsolved | `x_1 = 2, x_2 = 1` |
| **`the value 2x = 4`** | **`x = 2*exp(-2)/(a*h*l*t*u*v)`**, method symbolic, confidence 0.9 | abstains (`none`, confidence 0) |
| **`solve v = u + a*t for t`** | **`a = (-u + v)/t`** (wrong unknown) | `t = (-u + v)/a` |
| **`solve x + 1 = x + 1`** | **`no solution`** | `every value is a solution (identity)` |
| **`solve 3j = 6`** | **`no solution`** (Python lexes `3j` as 3i) | `j = 2` |
| `solve 0x + y = 1 and x + 0y = 2` | unsolved (`0x` lexed as hex) | `x = 2, y = 1` |
| `solve x^1000000 = 1` | killed by `timeout 60` (exit 124) | refused in about 1 s |
| `solve 2^999999999 = x` | 40 s in the logged run; killed at 60 s in an earlier one | refused in about 1 s |
| `balance H2 + O2 = H2O` | chemistry | chemistry (unchanged) |
| `If f(x) = 3x^2 + 2x, what is f'(x)?` | `6*x + 2` | `6*x + 2` (unchanged) |

Rows in bold were **confidently wrong** answers on `main`. The eval gate
couldn't see them because none of them is in the held-out suite.

## 4. Design decisions

1. **A new module (`study/equations.py`) instead of extending the regexes.**
   `main` had three overlapping regexes: two equations only, `solve` only, and a
   bare-equation fallback. The prose defect comes from sending unvetted text to
   implicit multiplication, and no regex can fix that. The new module owns
   notation → instruction → splitting → prose guard → solving, behind one
   function, `solve_equations(problem) -> WorkedSolution | None`.
   *Alternative considered:* loosen `_SYSTEM_RE` so `solve` is optional. That
   fixes the headline criterion in one line, but it leaves the
   two-equation limit, the Unicode gaps and the confidently wrong answers in
   place. Rejected.
2. **The prose guard works on tokens, not on sympy output.** Every identifier
   must be a variable (`x`, `x_1`), a sympy function, a constant, or a Greek
   name. A multi-letter name is accepted only when it is a juxtaposition of
   variables already used on their own (`xy` next to `x` and `y`). This rejects
   `the`/`value`/`Evaluate` and still accepts `xy = 6`.
3. **The `None` vs `SolverParseError` contract is kept.** Text that starts with
   an instruction (`solve`, `the system`) and contains broken maths raises the
   typed error, which the existing `test_solver_parse_errors.py` tests require.
   Text without an instruction is returned to the other solvers.
4. **`final_answer` is byte-identical to `main`'s format.** Tests and the eval
   scorer parse it. Extra explanation, such as "y is a free parameter" or "the
   determinant is 0", goes into the steps. Steps show `x^2`; the answer keeps
   sympy's `x**2`.
5. **The worked steps are computed, not narrated.** Gaussian elimination runs on
   exact rationals and is shown only when it agrees with `sympy.solve`; if they
   disagree, a warning is logged and the steps are left out. Every answer is
   substituted back into every equation. If the check fails, confidence drops
   from 0.9 to 0.6.
6. **Resource bounds go before sympy.** Literal exponents above 64 are rejected
   at the token level, because `2^999999999` stalls inside sympify itself.
   Computed powers (`x^(8*8*8)`) are rejected after parsing. At most 8
   equations are accepted.

## 5. Negative evidence

- **Mutation check:** disabling the prose guard makes 5 tests fail, and removing
  the number·name `*` insertion makes 2 fail. The suite detects both
  regressions.
- **Generated systems:** 40 seeded random non-singular 2×2/3×3 integer
  systems, in three notation styles and three separators, must reproduce the
  constructed solution and show back-substitution steps.

## 6. Risks and unverified conditions

- **Not covered by this branch:** `olivia ask` routes maths through
  `experts/math_expert.py`, which has its own `_SOLVE_RE` and is unchanged. The
  new notation support applies to `olivia solve`, the science expert, worksheets
  and MCP `olivia_solve`, all of which go through `solve_problem`. It does not
  apply to the math expert.
- **Pre-existing and unchanged:** `safe_sympify` still evaluates huge integer
  powers in the *arithmetic* path (`what is 2^999999999`, no `=`). This branch
  only guards the equation path. Should be a separate ticket.
- **Heuristic limits:** `f(x) = 2x` is read as implicit multiplication, as it
  was on `main`. A multi-letter variable name that isn't Greek and isn't a
  juxtaposition (`speed = 3`) is rejected as prose. That's deliberate: it
  abstains rather than guessing.
- **No LLM path was exercised.** Everything above ran offline with `NullClient`.
- **Pre-commit hook:** someone else's `pre-commit install` in the main checkout
  (T10, #18) is in the shared `.git/hooks`, and this branch has no
  `.pre-commit-config.yaml`. Commits were made with `PRE_COMMIT_ALLOW_NO_CONFIG=1`
  after running the CI-pinned ruff checks by hand (row 1). No hook was skipped,
  because none is configured on this branch.
