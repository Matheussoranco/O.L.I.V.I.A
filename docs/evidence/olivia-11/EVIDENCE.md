# Evidence Pack — `O.L.I.V.I.A #11` (`T3: Symbolic Solver Coverage >= 85%`)

- **Repository:** `Matheussoranco/O.L.I.V.I.A`
- **Issue:** `#11` (`T3: Symbolic Solver Coverage >= 85%`, parent `#8`)
- **Trace:** `olivia-11-t3`
- **Author:** Gemini 4 Neon (High reasoning effort, session `7f54c219-94aa-4eee-be8a-2152f9236c40`)
- **Branch / Worktree:** `feat/11-symbolic-solver-coverage` (`C:\Users\mathe\Documents\Code\O.L.I.V.I.A-wt11`, base `origin/main` @ `c1d797c5d7f5850caf00f8ba11a285cf86b2494d`)
- **Verification Status:** `PASS`
- **Merge Readiness:** `PENDING_REVIEW`

---

## 1. Executive Summary

Expanded O.L.I.V.I.A.'s deterministic symbolic solvers across **units**, **chemistry**, and **physics** with principled, general-purpose scientific modules (zero overfitting to the held-out eval dataset, zero modifications to `symbolic_solving.json`, and zero overlap with PR #27's `_sympify` / `_evaluate_arithmetic` changes).

| Metric | Baseline (`c1d797c`) | Target (`#11`) | Candidate | Delta |
|---|---:|---:|---:|---:|
| `symbolic.accuracy` | `78.1%` (50/64) | `>= 85%` | **`100.0%` (64/64)** | `+21.9 pp` |
| `symbolic.precision` | `100.0%` | `>= 97.6%` | **`100.0%` (64/64)** | `0.0 pp` |
| `symbolic.wrong_rate` | `0.0%` | `<= 1.57%` | **`0.0%` (0/64)** | `0.0 pp` |
| `symbolic.core.*` (all 4 domains) | `100.0%` | `100.0%` | **`100.0%`** | `0.0 pp` |
| `symbolic.reach.chemistry.accuracy` | `16.7%` (1/6) | `>= 70%` | **`100.0%` (6/6)** | `+83.3 pp` |
| `symbolic.reach.math.accuracy` | `100.0%` (10/10) | `>= 70%` | **`100.0%` (10/10)** | `0.0 pp` |
| `symbolic.reach.physics.accuracy` | `0.0%` (0/6) | `>= 70%` | **`100.0%` (6/6)** | `+100.0 pp` |
| `symbolic.reach.units.accuracy` | `0.0%` (0/3) | `>= 70%` | **`100.0%` (3/3)** | `+100.0 pp` |

---

## 2. Change Inventory

1. **`src/olivia/tools/units.py`:**
   - Added full English unit name and plural aliases (`metres`/`meters`, `miles`, `ounces`, `grams`, `seconds`, `nanometres`, etc.) applied in `_resolve()` before prefix expansion.
   - Added temperature-pair shorthand disambiguation (`C`/`F`/`K`) in `convert()` so `convert(25, "C", "F") == 77.0` while preserving `parse_unit("C")` as Coulomb and `convert(1, "C", "A*s") == 1.0`.
2. **`src/olivia/tools/chemistry.py`:**
   - Added `COMMON_COMPOUNDS`, `ELEMENT_NAMES`, `resolve_formula()`, `resolve_element()`, `percent_composition()`, and `oxidation_state()` (standard IUPAC rules with peroxide/hydride/`OF2` exceptions and clean abstention when >1 unknown element remains).
3. **`src/olivia/study/chemistry_solver.py` (new):**
   - Deterministic worked-solution solvers for percent composition by mass, oxidation states, mass ↔ moles conversions (with SI/imperial mass unit conversion), and complete combustion stoichiometry backed by `balance_equation()`.
4. **`src/olivia/study/physics_solver.py` (new):**
   - Deterministic worked-solution solvers backed by CODATA constants (`h`, `c`, `g`) and SI dimensional analysis: constant-acceleration kinematics, free fall, kinetic energy, Newton's second law, photon energy–wavelength–frequency, and simple pendulum.
5. **`src/olivia/study/solver.py`:**
   - Wired `_solve_chemistry`, `_solve_physics`, and `_solve_units` (including `"How many <to> in <val> <from>?"` and contextual `"<val> <from> ... How many <to> is that?"` guarded by dimensional compatibility). Untouched in `_sympify` and `_evaluate_arithmetic` to remain conflict-free with PR #27.
6. **`src/olivia/eval/datasets/gates.json`:**
   - Ratcheted `symbolic.symbolic.accuracy` and `symbolic.symbolic.coverage` floors to `0.85` and added `0.70` floors for all four `symbolic.symbolic.reach.*.accuracy` domains.
7. **`tests/test_study/test_scientific_solvers.py` (new):**
   - Disjoint generalization & abstention unit tests covering all new units, chemistry, and physics capabilities on held-out problems not in `symbolic_solving.json`.

---

## 3. Verification Results

| # | Command | Exit Code | Observed Result |
|---|---|---|---|
| 1 | `uv run --no-sync ruff check --no-cache src/ tests/` | `0` | `All checks passed!` |
| 2 | `uv run --no-sync ruff format --no-cache --check src/ tests/` | `0` | `93 files already formatted` |
| 3 | `uv run --no-sync mypy src/olivia` | `0` | `Success: no issues found in 67 source files` |
| 4 | `uv run --no-sync pytest tests/ --tb=short -q` | `0` | `392 passed, 2 skipped` (15 new disjoint scientific solver tests) |
| 5 | `uv run --no-sync olivia eval --check` | `0` | `All gates hold.` (`symbolic.accuracy = 100.0%` [64/64], `wrong_rate = 0.0%`, all 4 core & all 4 reach domains `100.0%`) |

---

## 4. Generalisation & Review Follow-Up (Round 2)

- **Held-out vs. fresh generalisation:** The `100.0%` (64/64) score above is measured on the repository's existing held-out `symbolic_solving.json` suite (unmodified). Independently during review of `d9a70f7`, Claude Code evaluated 30 freshly authored problems with hand-computed answers and observed **29/30 correct, 1 honest abstention, 0 wrong** (vs. `1/30` on `origin/main`), providing independent generalisation evidence.
- **Review defects resolved:**
  1. **Lead blocker (`physics_solver.py`):** Separated question-clause parsing (`_asked_kinematic_quantity`) from supplied givens so initial velocity phrasing does not hijack displacement queries (`3 m/s`, `2 m/s^2`, `4 s` → `28 m` displacement, `11 m/s` final velocity).
  2. **Claude blocker (`physics_solver.py`):** Added deceleration/braking/slowing-down sign handling (`_DECEL_RE`) and physical stop-time guarding (`20 m/s` decelerating at `4 m/s^2` → `8 m/s` at `3 s`, `0 m/s` at `5 s`, honest abstention beyond `5 s`).
