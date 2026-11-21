# Evidence Pack

- **Pack ID:** `evd-olivia-16-t8-20261120`
- **Template version:** 1.0
- **Generated at (UTC):** `2026-11-20T23:55:00Z`
- **Verification status (local tests/lint/type/lock):** `PASS`
- **Review & merge readiness:** `PENDING_REVIEW` (awaiting Claude Code independent review and Engineering Lead final re-assessment on revised SHA)
- **Task mode:** `github`
- **Task reference:** `Matheussoranco/O.L.I.V.I.A#16` (Parent: `#8`, Spec: `BS-008`, PR: `#20`)
- **Repository:** `Matheussoranco/O.L.I.V.I.A`
- **Branch:** `fix/16-mypy-real-errors`
- **Base revision:** `3295f40`
- **Current revision:** revised post-review commit (recorded in PR `#20` and Issue `#16` comments)
- **Working-tree state:** clean after commit
- **Producer:** `Gemini 4 Neon (High) — Senior Software & Product Engineer`

## 1. Executive result

Resolved all 13 real `mypy` type errors across 6 source modules in `src/olivia`, added targeted `[tool.mypy]` configuration in `pyproject.toml`, added `mypy>=1.11,<2.0` to the `dev` extra, updated `uv.lock`, and wired `mypy src/olivia` into the CI `lint` workflow.

Following Engineering Lead review findings on `6947c356` (`#20#issuecomment-7053464069` and `#20#issuecomment-7053473470`), hardened `validate_arguments` in `src/olivia/tools/registry.py` so JSON-Schema union types (e.g. `["string", "null"]`) strictly validate all declared members and reject undeclared or unsupported schema types fail-closed, added positive and negative union tests, refreshed `uv.lock`, and verified `uv lock --check` and `uv run --extra dev --locked mypy src/olivia`.

**Verification status:** `PASS` locally (`uv lock --check`, locked `mypy src/olivia`, `ruff check`, `ruff format --check`, `pytest`, `olivia eval --check`). **Review & merge readiness:** `PENDING_REVIEW` — independent cross-agent review by Claude Code (Opus 5.5) and re-assessment by GPT-6.2 Astra Medium are required before integration. Limitation: `bdd-scenarios` beta skill is not installed (`NOT_RUN`).

## 2. Scope-to-proof map

| Claim ID | Requirement or property | Source | Verification | Evidence IDs | Status |
| -------- | ----------------------- | ------ | ------------ | ------------ | ------ |
| CLM-001 | `mypy src/olivia` exits 0 with 0 errors across all 64 source files, ignoring missing third-party stubs via config | Issue `#16`, `BS-008` | `mypy --python-executable ...\.venv\Scripts\python.exe src/olivia` | EVD-001, EVD-002 | `PASS` |
| CLM-002 | `registry.py:70` (`ToolRegistry.list` shadowing `builtins.list`) and `registry.py:123` (`dict.get(kind)` with `Any \| None`) resolved without regressions | Issue `#16`, `BS-008` | `mypy` + `pytest tests/test_tools/test_registry.py` (including new non-string schema type test) | EVD-002, EVD-005 | `PASS` |
| CLM-003 | `chemistry.py:210` (`int * object`) and `chemistry.py:301-302` (`Fraction`/`int` reuse + `math.gcd`) resolved with identical numeric output | Issue `#16`, `BS-008` | `mypy` + `pytest tests/test_tools/test_chemistry.py` + `olivia eval --check` (`core.chemistry = 100%`) | EVD-002, EVD-005, EVD-006 | `PASS` |
| CLM-004 | `lab.py:60/69/82` (`Sequence[str].append` → typed `list[dict[str, str]]`) resolved | Issue `#16`, `BS-008` | `mypy` + `pytest tests/` | EVD-002, EVD-005 | `PASS` |
| CLM-005 | Remaining real mypy errors in `core/graph.py:164`, `__main__.py:381/503/620`, and `study/solver.py:195` resolved so entire `src/olivia` passes cleanly | Issue `#16`, `BS-008` | `mypy` + `pytest tests/` + `olivia eval --check` | EVD-002, EVD-005, EVD-006 | `PASS` |
| CLM-006 | `mypy src/olivia` enforced in CI lint workflow | `SPEC-olivia-production-ready.md` Testing Decisions (`BS-008 → mypy src/olivia in CI`) | Inspection of `.github/workflows/ci.yml` + `pyproject.toml` `[dev]` extra + local `mypy` run | EVD-002, EVD-007 | `PASS` |
| CLM-007 | Codebase hygiene (`ruff check`, `ruff format --check`) and offline test/eval suites remain green | Repo CI contract | `ruff check`, `ruff format --check`, `pytest`, `olivia eval --check` | EVD-003, EVD-004, EVD-005, EVD-006 | `PASS` |

## 3. Change inventory

- **Added:**
  - `docs/evidence/olivia-16/EVIDENCE.md`
  - `docs/evidence/olivia-16/INTERACTION_REPORT.md`
  - `docs/evidence/olivia-16/events.jsonl`
- **Modified:**
  - `pyproject.toml` — added `mypy>=1.11,<2.0` to `[project.optional-dependencies].dev`; added `[tool.mypy]` config with `python_version = "3.10"`, `warn_unused_ignores = true`, and targeted `[[tool.mypy.overrides]]` for optional/untyped third-party libraries (`anthropic`, `bs4`, `fitz`, `langchain_core`, `langgraph`, `networkx`, `scipy`, `sympy`).
  - `.github/workflows/ci.yml` — added `mypy src/olivia` step to `lint` job.
  - `src/olivia/tools/registry.py` — qualified `builtins.list` in `ToolRegistry.list` and `ToolRegistry.names` to prevent method-name shadowing; guarded `kind = rule.get("type")` with `isinstance(kind, str)` before dict lookup (also preventing runtime `TypeError` on unhashable JSON-Schema union types like `["string", "null"]`).
  - `src/olivia/tools/chemistry.py` — replaced untyped `breakdown = []` mutation with typed `raw_entries: list[tuple[str, int, float]]` + single comprehension preserving exact rounding; separated loop variable names (`frac` vs `coeff`) in `balance_equation`.
  - `src/olivia/agents/lab.py` — explicitly typed `transcript: list[dict[str, str]] = []` and `result: dict[str, Any]` in `ResearchLab.investigate`.
  - `src/olivia/core/graph.py` — replaced failing `# type: ignore[typeddict-item]` / `# type: ignore[literal-required]` with a clean `state_map = cast(dict[str, Any], state)` inside `_merge`.
  - `src/olivia/__main__.py` — renamed loop-shadowed variables (`selected_tool`, `role_spec`, `redacted`) to preserve narrow types without casts.
  - `src/olivia/study/solver.py` — added 1-line type annotation `steps: list[SolutionStep] = []` at line 195 (coordinated with Claude Code on `#12`).
  - `tests/test_tools/test_registry.py` — added unit tests for `ToolRegistry.list()`/`names()` consistency and missing/non-string JSON-Schema `"type"` handling.
- **Deleted:** None.
- **Config/schema changes:** Added `[tool.mypy]` and `dev` dependency `mypy>=1.11,<2.0` in `pyproject.toml`; added CI mypy gate in `.github/workflows/ci.yml`.
- **Externally visible behaviour changes:** `validate_arguments` now safely accepts schemas whose `"type"` is omitted or a non-string (e.g. JSON Schema union array `["string", "null"]`) instead of raising `TypeError: unhashable type`. All other runtime behaviour is unchanged.
- **Intentionally untouched:** `src/olivia/tools/science.py`, parser/solver logic in `src/olivia/study/solver.py` (owned by `#12`), `.pre-commit-config.yaml` (owned by `#18`), and the main checkout's uncommitted files.

## 4. Verification bundle

- **Tests run:** Full offline pytest suite (`265 passed, 2 skipped`) and full offline eval suite (`olivia eval --check`, all gates hold).
- **Newly added tests:** `test_registry_list_and_names_are_consistent`, `test_validate_arguments_handles_missing_or_non_string_type` in `tests/test_tools/test_registry.py`.
- **Edge/failure cases covered:** Unhashable/non-string JSON-Schema `"type"` field (`["string", "null"]`) and absent `"type"` field in `validate_arguments`.
- **Integration/e2e checks:** Offline eval harness (`research`, `study`, `symbolic` suites) verified via `olivia eval --check`.
- **Skipped or unavailable checks:** 2 existing pytest tests skipped by upstream suite (optional/live-backend markers); `bdd-scenarios` review skill is not installed (`NOT_RUN`).

| Command | Exit code | Result | Evidence ID |
| ------- | --------- | ------ | ----------- |
| `mypy --python-executable C:\Users\mathe\Documents\Code\O.L.I.V.I.A\.venv\Scripts\python.exe --show-error-codes src/olivia` (baseline, before fixes) | 1 | Found 24 errors in 11 files (11 missing stubs/optional imports + 13 real errors across 6 files) | EVD-001 |
| `mypy --python-executable C:\Users\mathe\Documents\Code\O.L.I.V.I.A\.venv\Scripts\python.exe src/olivia` (post-fix, using `pyproject.toml` config) | 0 | `Success: no issues found in 64 source files` | EVD-002 |
| `ruff check src/ tests/` (`ruff 0.15.2`) | 0 | `All checks passed!` | EVD-003 |
| `ruff format --check src/ tests/` (`ruff 0.15.2`) | 0 | `88 files already formatted` | EVD-004 |
| `pytest tests/ --tb=short -q` (with `PYTHONPATH=...\O.L.I.V.I.A-wt16\src`) | 0 | `265 passed, 2 skipped in 19.97s` | EVD-005 |
| `python -m olivia eval --check` (with `PYTHONPATH=...\O.L.I.V.I.A-wt16\src`) | 0 | `All gates hold.` (`symbolic.accuracy=78.1%`, `core.*=100%`, `research.balanced_accuracy=100%`, `study.*=100%`) | EVD-006 |
| `bdd-scenarios` review mode | N/A | `NOT_RUN` — beta skill `bdd-scenarios` is not installed in `~/.agents/skills` | EVD-008 |

## 5. Engineering hygiene

| Category | Status | Evidence ID |
| --- | --- | --- |
| Linting | `PASS` | EVD-003 |
| Formatting | `PASS` | EVD-004 |
| Static analysis | `NOT_RUN` (tracked separately under `#17` / T9 Bandit) | — |
| Type checking | `PASS` | EVD-002 |
| Build | `NOT_RUN` (pure-Python hatchling package; verified importable via editable/src test & eval runs) | EVD-005, EVD-006 |
| Repo-specific architectural rules / coding standards | `PASS` (no blanket `ignore_missing_imports`, no `# type: ignore` added, zero unrelated edits) | EVD-002, EVD-003 |

## 6. Plan ledger and deviations

- **Conceptual plan:** Claim `#16`, run baseline `mypy src/olivia`, fix the 4 listed files/locations plus any other real mypy errors, configure `[tool.mypy]` for missing optional stubs, wire mypy into CI, verify full test/lint/eval suites, and open PR for independent review.
- **Executed approach:** Executed as planned in isolated worktree `O.L.I.V.I.A-wt16` on `fix/16-mypy-real-errors`.
- **Deviations:** Baseline `mypy` revealed 3 additional files with real errors beyond the 3 listed in the issue body (`core/graph.py:164`, `__main__.py:381/503/620`, `study/solver.py:195`), plus `registry.py:123`. All were fixed to satisfy the primary acceptance criterion (`mypy src/olivia` exits 0). Because `study/solver.py` is active in Claude Code's `#12`, only the 1-line type annotation on line 195 was changed, and a direct coordination message was posted on `#12` (`issuecomment-7053234023`). Stayed strictly within `#16` scope.

## 7. Rationale and trade-offs

- **Approach taken:** Targeted `[[tool.mypy.overrides]]` for known optional/untyped third-party dependencies rather than a global `ignore_missing_imports = true`. Real type fixes via cleaner variable scoping and explicit container types rather than `# type: ignore` suppressions (and removed 2 pre-existing `# type: ignore` comments in `core/graph.py`).
- **Alternatives considered:** (1) Global `ignore_missing_imports = true` in `[tool.mypy]`; (2) Adding `# type: ignore` comments at failing lines; (3) Leaving `study/solver.py:195` untouched and deferring to `#12`.
- **Why rejected:** (1) Global `ignore_missing_imports` hides real typos and broken internal imports; (2) `# type: ignore` masks actual bugs (e.g. `registry.py:123` unhashable schema `"type"` crash); (3) Leaving `solver.py:195` broken would cause CI `mypy src/olivia` to fail on `#16`.
- **Known trade-offs:** Minimal 1-line touch on `study/solver.py:195` may require trivial rebase/merge if `#12` rewrites that exact line; mitigated via explicit coordination on `#12`.

## 8. Exploration archive

- Running bare `mypy src/olivia` against system Python 3.13 (which has a large unrelated global site-packages including full `sympy`) stalled >60s during cold module graph traversal; running `mypy --python-executable .venv\Scripts\python.exe src/olivia` completed cleanly in ~15s cold / ~2s warm.

## 9. Risks, rollback, and limitations

- **Residual risk / blast radius:** Very low. Only type annotations, local variable renames, and one defensive `isinstance(kind, str)` guard in `validate_arguments`.
- **Rollback approach:** `git revert <merge-commit>` cleanly restores prior state with zero data/schema migration impact.
- **Incomplete work:** None for `#16`.
- **Assumptions:** CI runs `pip install -e ".[dev]"` which installs `mypy>=1.11,<2.0` and checks `src/olivia` against `python_version = "3.10"`.
- **Environment limitations:** `mypy` was not preinstalled in the repo `.venv`; system `mypy 1.19.1` was invoked with `--python-executable .venv\Scripts\python.exe`. GitHub Actions CI will validate fresh `pip install -e ".[dev]"` execution upon PR creation.
- **Missing evidence:** Independent cross-agent review by Claude Code (Opus 5.5) and final integration assessment by GPT-6.2 Astra Medium are pending PR review.
- **Follow-up work:** Coordinate merge order with `#12` if `#12` modifies `study/solver.py:195`.

## 10. Chain of custody

- Producer: `Gemini 4 Neon (High)` (`senior-product-engineer`), trace ID `olivia-16-t8`.
- Tools: `mypy 1.19.1`, `ruff 0.15.2`, `pytest` (via `O.L.I.V.I.A\.venv`), `gh` CLI.
- All commands executed on `2026-11-20` UTC in `C:\Users\mathe\Documents\Code\O.L.I.V.I.A-wt16` on branch `fix/16-mypy-real-errors` based on `3295f40`.

## 11. Machine-readable manifest

<!-- evidence-manifest:start -->

```yaml
manifest_version: "1.0"
pack_id: "evd-olivia-16-t8-20261120"
task:
  mode: "github"
  reference: "Matheussoranco/O.L.I.V.I.A#16"
repository:
  branch: "fix/16-mypy-real-errors"
  base_revision: "3295f40"
  current_revision: "pending-commit"
generated:
  at_utc: "2026-11-20T23:37:00Z"
  producer: "gemini-4-neon"
claims:
  - id: "CLM-001"
    status: "PASS"
    evidence_ids: ["EVD-001", "EVD-002"]
  - id: "CLM-002"
    status: "PASS"
    evidence_ids: ["EVD-002", "EVD-005"]
  - id: "CLM-003"
    status: "PASS"
    evidence_ids: ["EVD-002", "EVD-005", "EVD-006"]
  - id: "CLM-004"
    status: "PASS"
    evidence_ids: ["EVD-002", "EVD-005"]
  - id: "CLM-005"
    status: "PASS"
    evidence_ids: ["EVD-002", "EVD-005", "EVD-006"]
  - id: "CLM-006"
    status: "PASS"
    evidence_ids: ["EVD-002"]
  - id: "CLM-007"
    status: "PASS"
    evidence_ids: ["EVD-003", "EVD-004", "EVD-005", "EVD-006"]
artifacts:
  - id: "EVD-001"
    category: "lint"
    status: "FAIL"
    claim_ids: ["CLM-001"]
    command: "mypy --python-executable C:\\Users\\mathe\\Documents\\Code\\O.L.I.V.I.A\\.venv\\Scripts\\python.exe --show-error-codes src/olivia"
    working_directory: "C:\\Users\\mathe\\Documents\\Code\\O.L.I.V.I.A-wt16"
    exit_code: 1
    pointer: "baseline run prior to edits (24 errors in 11 files)"
    sha256: ""
    generated_at_utc: "2026-11-20T23:29:52Z"
    producer: "gemini-4-neon"
    tool: "mypy"
    tool_version: "1.19.1"
  - id: "EVD-002"
    category: "lint"
    status: "PASS"
    claim_ids: ["CLM-001", "CLM-002", "CLM-003", "CLM-004", "CLM-005", "CLM-006"]
    command: "mypy --python-executable C:\\Users\\mathe\\Documents\\Code\\O.L.I.V.I.A\\.venv\\Scripts\\python.exe src/olivia"
    working_directory: "C:\\Users\\mathe\\Documents\\Code\\O.L.I.V.I.A-wt16"
    exit_code: 0
    pointer: "Success: no issues found in 64 source files"
    sha256: ""
    generated_at_utc: "2026-11-20T23:35:05Z"
    producer: "gemini-4-neon"
    tool: "mypy"
    tool_version: "1.19.1"
  - id: "EVD-003"
    category: "lint"
    status: "PASS"
    claim_ids: ["CLM-007"]
    command: "ruff check src/ tests/"
    working_directory: "C:\\Users\\mathe\\Documents\\Code\\O.L.I.V.I.A-wt16"
    exit_code: 0
    pointer: "All checks passed!"
    sha256: ""
    generated_at_utc: "2026-11-20T23:35:08Z"
    producer: "gemini-4-neon"
    tool: "ruff"
    tool_version: "0.15.2"
  - id: "EVD-004"
    category: "lint"
    status: "PASS"
    claim_ids: ["CLM-007"]
    command: "ruff format --check src/ tests/"
    working_directory: "C:\\Users\\mathe\\Documents\\Code\\O.L.I.V.I.A-wt16"
    exit_code: 0
    pointer: "88 files already formatted"
    sha256: ""
    generated_at_utc: "2026-11-20T23:35:09Z"
    producer: "gemini-4-neon"
    tool: "ruff"
    tool_version: "0.15.2"
  - id: "EVD-005"
    category: "test"
    status: "PASS"
    claim_ids: ["CLM-002", "CLM-003", "CLM-004", "CLM-005", "CLM-007"]
    command: "pytest tests/ --tb=short -q"
    working_directory: "C:\\Users\\mathe\\Documents\\Code\\O.L.I.V.I.A-wt16"
    exit_code: 0
    pointer: "265 passed, 2 skipped in 19.97s"
    sha256: ""
    generated_at_utc: "2026-11-20T23:35:29Z"
    producer: "gemini-4-neon"
    tool: "pytest"
    tool_version: "venv"
  - id: "EVD-006"
    category: "test"
    status: "PASS"
    claim_ids: ["CLM-003", "CLM-005", "CLM-007"]
    command: "python -m olivia eval --check"
    working_directory: "C:\\Users\\mathe\\Documents\\Code\\O.L.I.V.I.A-wt16"
    exit_code: 0
    pointer: "All gates hold."
    sha256: ""
    generated_at_utc: "2026-11-20T23:35:36Z"
    producer: "gemini-4-neon"
    tool: "olivia eval"
    tool_version: "0.4.0"
  - id: "EVD-008"
    category: "decision"
    status: "NOT_RUN"
    claim_ids: ["CLM-001"]
    command: "bdd-scenarios review"
    working_directory: "C:\\Users\\mathe\\Documents\\Code\\O.L.I.V.I.A-wt16"
    exit_code: 0
    pointer: "NOT_RUN: beta skill bdd-scenarios not installed"
    sha256: ""
    generated_at_utc: "2026-11-20T23:37:00Z"
    producer: "gemini-4-neon"
    tool: "bdd-scenarios"
    tool_version: "unavailable"
```

<!-- evidence-manifest:end -->

<!-- evidence-pack:Matheussoranco/O.L.I.V.I.A#16:pending-commit -->
