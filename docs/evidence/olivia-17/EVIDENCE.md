# Evidence Pack

- **Pack ID:** olivia-17-207ff4d
- **Template version:** 1.0
- **Generated at (UTC):** 2026-11-22T01:07:02Z
- **Overall status:** PASS for the claims below
- **Task mode:** github
- **Task reference:** Matheussoranco/O.L.I.V.I.A#17
- **Repository:** Matheussoranco/O.L.I.V.I.A
- **Branch:** fix/bandit-findings-t17-v2
- **Base revision:** c1d797c5d7f5850caf00f8ba11a285cf86b2494d
- **Current revision:** 207ff4d9e0245ef9efee774fc7b1ba2840f91917 (the code revision tested)
- **Working-tree state:** clean source revision at 207ff4d; evidence files composed afterward
- **Producer:** Codex lead

## 1. Executive result

PR #26 now installs published defusedxml type stubs in its development environment. The lockfile, lint, formatting, typing, offline tests and eval all passed locally. Bandit reported no medium or high findings with Python 3.12. Three accepted low-severity findings remain.

## 2. Scope-to-proof map

| Claim ID | Requirement or property | Source | Verification | Evidence IDs | Status |
| -------- | ------------------------ | ------ | ------------- | ------------ | ------ |
| CLM-001 | The lint environment resolves the XML parser's types | PR #26 review | Baseline mypy failure, locked install, and mypy rerun | EVD-001, EVD-002 | PASS |
| CLM-002 | Ruff formatting and offline behavior checks pass | CI workflow | Ruff, pytest and offline eval | EVD-003, EVD-004, EVD-005 | PASS |
| CLM-003 | No medium or high Bandit findings | Issue #17 severity criterion | JSON scan of base and candidate under Python 3.12 | EVD-006 | PASS |

## 3. Change inventory

- **Added:** Development-only types-defusedxml dependency.
- **Modified:** pyproject.toml and uv.lock.
- **Deleted:** None.
- **Config/schema changes:** Development dependency list.
- **Externally visible behaviour changes:** None from the stubs.
- **Intentionally untouched:** Ruff and mypy settings, runtime parser code, and the vendored skills tree in this follow-up.

## 4. Verification bundle

- **Tests run:** Entire offline test suite and offline eval on CPython 3.12.10.
- **Newly added tests:** None for this dependency repair.
- **Edge/failure cases covered:** Mypy reproduces the missing-stub import failure before the dependency change.
- **Integration/e2e checks:** Locked environment sync and offline evaluation.
- **Skipped or unavailable checks:** Two pytest skips. Live LLM fallback unconfigured and excluded from offline eval.

| Command | Exit code | Result | Evidence ID |
| ------- | --------- | ------ | ----------- |
| uv run --locked --extra dev --extra science mypy src/olivia (3d7f3c5) | 1 | Two import-untyped findings for defusedxml | EVD-001 |
| uv lock --check; uv sync --locked --extra dev --extra science; mypy src/olivia | 0 each | 75 locked packages, stubs installed, 65 source files pass | EVD-002 |
| ruff check --no-cache src/ tests/; ruff format --no-cache --check src/ tests/ | 0 each | Lint clean, 90 files already formatted | EVD-003 |
| python -m pytest tests/ --tb=short -q | 0 | 377 passed, 2 skipped | EVD-004 |
| olivia eval --check | 0 | All gates hold | EVD-005 |
| uvx --python 3.12 --from bandit==1.8.6 bandit -r src/olivia -f json -o REPORT -q | 1 at both revisions | Base: 2 medium, 5 low. Candidate: 0 medium, 3 low. No scanner errors in either report. | EVD-006 |

Commands using project executables ran in the environment created by the locked sync.

## 5. Engineering hygiene

| Category | Status | Evidence ID |
| --- | --- | --- |
| Linting | PASS | EVD-003 |
| Formatting | PASS | EVD-003 |
| Static analysis | PASS for the issue's severity threshold | EVD-006 |
| Type checking | PASS | EVD-002 |
| Build | NOT_RUN for a distributable wheel | |
| Repo-specific architectural rules / coding standards | NOT_RUN | |

## 6. Plan ledger and deviations

- **Conceptual plan:** Reproduce the CI failure and restore typing through the dev extra.
- **Executed approach:** Reproduced the failure, installed published stubs through the lockfile, and reran the project gates.
- **Deviations:** Ruff cache writes produced an access warning when lint and format ran together on Windows. Repeated both sequentially with caching disabled. An initial Bandit run under the default interpreter reported scanner errors. Discarded that result and repeated both scans under Python 3.12.

## 7. Rationale and trade-offs

- **Approach taken:** Use published type stubs as a development dependency.
- **Alternatives considered:** A dependency-specific mypy exclusion.
- **Why rejected:** The stubs preserve type checking of the imported API.
- **Known trade-offs:** The development environment installs one additional package.

## 8. Exploration archive

The original type failure is in GitHub Actions run 44966467315, job 137036512775. The subsequent local reproduction emitted the same two import diagnostics.

## 9. Risks, rollback, and limitations

- **Residual risk / blast radius:** Development environment and lockfile.
- **Rollback approach:** Revert the stub dependency and lockfile change together.
- **Incomplete work:** The three low Bandit findings B404, B110 and B603 remain. The severity criterion permits low findings. The specific subprocess and resource-limit recommendations in issue #17 remain open.
- **Assumptions:** Local results apply to the code revision listed above.
- **Environment limitations:** Local checks ran on Windows with CPython 3.12.10.
- **Missing evidence:** Hosted CI and renewed independent review on the complete PR revision were pending when this pack was prepared.
- **Follow-up work:** Review the new PR revision and assess the remaining low findings separately.

## 10. Chain of custody

Codex lead executed the commands in the isolated olivia-26-ci worktree. Bandit 1.8.6 scanned an archive of c1d797c and the candidate source. The local summary records scanner error counts, finding IDs, severity totals, commands, and timestamps. The PR will carry the hosted CI run for the updated revision.

## 11. Machine-readable manifest

<!-- evidence-manifest:start -->
```yaml
manifest_version: "1.0"
pack_id: "olivia-17-207ff4d"
task:
  mode: "github"
  reference: "Matheussoranco/O.L.I.V.I.A#17"
repository:
  branch: "fix/bandit-findings-t17-v2"
  base_revision: "c1d797c5d7f5850caf00f8ba11a285cf86b2494d"
  current_revision: "207ff4d9e0245ef9efee774fc7b1ba2840f91917"
generated:
  at_utc: "2026-11-22T01:07:02Z"
  producer: "Codex lead"
claims:
  - id: "CLM-001"
    status: "PASS"
    evidence_ids: ["EVD-001", "EVD-002"]
  - id: "CLM-002"
    status: "PASS"
    evidence_ids: ["EVD-003", "EVD-004", "EVD-005"]
  - id: "CLM-003"
    status: "PASS"
    evidence_ids: ["EVD-006"]
artifacts:
  - {id: "EVD-001", category: "log", status: "PASS", claim_ids: ["CLM-001"], command: "baseline mypy src/olivia", exit_code: 1}
  - {id: "EVD-002", category: "test", status: "PASS", claim_ids: ["CLM-001"], command: "locked sync and mypy src/olivia", exit_code: 0}
  - {id: "EVD-003", category: "lint", status: "PASS", claim_ids: ["CLM-002"], command: "Ruff lint and format", exit_code: 0}
  - {id: "EVD-004", category: "test", status: "PASS", claim_ids: ["CLM-002"], command: "python -m pytest tests/ --tb=short -q", exit_code: 0}
  - {id: "EVD-005", category: "test", status: "PASS", claim_ids: ["CLM-002"], command: "olivia eval --check", exit_code: 0}
  - {id: "EVD-006", category: "log", status: "PASS", claim_ids: ["CLM-003"], command: "Bandit 1.8.6 JSON scan on CPython 3.12", exit_code: 1}
```
<!-- evidence-manifest:end -->

<!-- evidence-pack:Matheussoranco/O.L.I.V.I.A#17:207ff4d9e0245ef9efee774fc7b1ba2840f91917 -->
