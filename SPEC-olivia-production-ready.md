## Problem Statement

O.L.I.V.I.A. (Open Learning Intelligence & Virtual Investigation Assistant) is an autonomous agent specialized in study, learning, scientific research, and discovery. It is built on the I.S.A.A.C. architecture but is a separate codebase. The current version (0.4.0-alpha) works fully offline with deterministic symbolic fallbacks, but several capabilities required for daily production use by Matheus are missing or incomplete:

- No LLM backend configured (both Anthropic and Ollama need setup)
- Symbolic solver coverage is 65.6% (target ≥85%)
- Equation parser cannot handle systems of equations or common notation variants
- Interactive tutor mode, flashcard/worksheet generation from source documents, and MCP co-working with Claude Code are untested with real LLMs
- Code quality gates (mypy real errors, bandit findings) and pre-commit hygiene are pending

This spec captures the agreed ticket set (T1–T10) to make O.L.I.V.I.A. production-ready for Matheus's daily research and study workflows.

## Solution

Execute ten tickets in dependency order to configure backends, validate the core research loop, raise solver/parser quality, complete LLM-dependent features, and harden code quality. The tickets are:

- **T1**: Configure Ollama + Anthropic backends (unblocks T2, T5, T6, T7)
- **T2**: Real end-to-end research cycle with Anthropic (validates core loop)
- **T3**: Symbolic solver coverage ≥85% (independent)
- **T4**: Equation parser: systems + edge cases (independent)
- **T5**: Interactive tutor mode (requires T1)
- **T6**: Flashcard/worksheet/quiz generation from PDF/arXiv (requires T1)
- **T7**: MCP co-working with Claude Code (requires T1)
- **T8**: Fix mypy real errors (parallel)
- **T9**: Address bandit findings (parallel)
- **T10**: Ruff pre-commit hook

## Stories

### US-001 — Daily research with real LLM backend

**Type:** User Story

As Matheus, I want to run `olivia research "question" --network` and get a useful DiscoveryReport with falsifiable hypotheses, runnable experiments, effect-size analyses, Popperian critique, and a complete IMRaD report, so that I can use O.L.I.V.I.A. for actual research projects.

### US-002 — Daily study workflow with real LLM backend

**Type:** User Story

As Matheus, I want to generate flashcards, worksheets, and quizzes from PDFs/arXiv papers (`olivia study cards/worksheet/quiz --content-file`), run interactive Socratic tutoring (`olivia tutor "topic"`), and have all content grounded in the source, so that I can use O.L.I.V.I.A. for learning new domains.

### US-003 — MCP co-working with Claude Code

**Type:** User Story

As Matheus, I want to call all 17 O.L.I.V.I.A. tools from Claude Code via MCP (`olivia_ask`, `olivia_solve`, `olivia_research`, `olivia_worksheet`, `molar_mass`, `balance_equation`, `convert_units`, `physical_constant`, `notebook_*`, `meta_stats`, `ping`), so that I can delegate research/study tasks to O.L.I.V.I.A. while working in Claude.

### US-004 — Symbolic STEM solving covers my daily needs

**Type:** User Story

As Matheus, I want `olivia solve` to handle systems of equations, implicit multiplication, caret powers, and all core physics/chemistry/math/units domains at ≥85% accuracy, so that I rarely hit the "unsolvable offline" fallback.

### DS-001 — LLM backend configuration persisted locally

**Type:** Data Story

The `.env` file at the repo root holds `OLIVIA_LLM__PROVIDER`, `OLIVIA_LLM__MODEL`, `OLIVIA_LLM__OLLAMA_MODEL`, and `ANTHROPIC_API_KEY` (gitignored). `olivia info` reflects the active backend and availability.

### MS-001 — Solver coverage metric

**Type:** Model Story

The symbolic solver's accuracy on the held-out eval suite (`olivia eval --check`) must reach ≥85% overall, with each reach domain (physics, units, math, chemistry) ≥70%. Core domains remain at 100%.

### AS-001 — Research cycle agent behavior

**Type:** Agent Story

The research cycle (literature → hypothesis → experiment → analysis → critique → report) executes end-to-end with a real LLM, producing a DiscoveryReport where every hypothesis has status `supported` or `refuted` (not `inconclusive`), and all IMRaD sections contain non-template content.

## Behavioral Specifications

### BS-001 — LLM backend configuration and availability

**Stories:** DS-001, US-001, US-002, US-003

```gherkin
Feature: LLM backend configuration

  Scenario: Both backends configured and available
    Given a .env file with OLIVIA_LLM__PROVIDER=anthropic, ANTHROPIC_API_KEY set, and OLIVIA_LLM__OLLAMA_MODEL=llama3.1:8b
    And Ollama is running with llama3.1:8b pulled
    When I run `olivia info`
    Then the output shows "Active backend: anthropic" (or "auto")
    And "Backend available: True"
    And both "anthropic" and "ollama" are listed as available providers
```

### BS-002 — Real end-to-end research cycle produces useful DiscoveryReport

**Stories:** US-001, AS-001

```gherkin
Feature: Research cycle with real LLM

  Scenario: Complete research cycle with all quality gates
    Given Anthropic backend is configured and available
    When I run `olivia research "Does spaced repetition beat massed practice?" --network`
    Then the output contains a DiscoveryReport with:
      | section          | requirement                                           |
      | Literature       | ≥3 retrieved papers cited                             |
      | Hypotheses       | ≥3 falsifiable hypotheses with predictions + tests   |
      | Experiments      | ≥1 design with variables + power analysis             |
      | Analysis         | Effect size (Cohen's d), p-value, 95% CI            |
      | Critique         | Popperian critique: flags flaw OR confirms clean      |
      | Report (IMRaD)   | Introduction, Methods, Results, Discussion populated |
      | Hypothesis status| Each is "supported" or "refuted" (not "inconclusive") |
```

### Unresolved behavior

- The specific research question for validation is not fixed; "Does spaced repetition beat massed practice?" was used as an example during grilling. Any well-studied question with available literature works.
- Whether the cycle should auto-revise hypotheses up to `max_revisions` (default 3) or stop at first clean critique was not explicitly decided — the architecture supports both.

### BS-003 — Symbolic solver coverage meets threshold

**Stories:** US-004, MS-001

```gherkin
Feature: Symbolic solver eval gate

  Scenario: Overall accuracy ≥85% and each reach domain ≥70%
    Given the eval datasets are unchanged
    When I run `olivia eval --check`
    Then the output shows "symbolic.accuracy ≥ 85%"
    And "symbolic.reach.physics.accuracy ≥ 70%"
    And "symbolic.reach.units.accuracy ≥ 70%"
    And "symbolic.reach.math.accuracy ≥ 70%"
    And "symbolic.reach.chemistry.accuracy ≥ 70%"
    And all "symbolic.core.*" remain at 100%
```

### BS-004 — Equation parser handles systems and notation variants

**Stories:** US-004

```gherkin
Feature: Equation parser extensions

  Scenario: System of equations in natural language
    Given the parser is extended
    When I run `olivia solve "the system 2x + y = 10 and x - y = 2"`
    Then the output shows worked steps and "Answer: x = 4, y = 2"

  Scenario: Comma-separated system
    When I run `olivia solve "solve 2x + y = 10, x - y = 2"`
    Then the output shows worked steps and "Answer: x = 4, y = 2"

  Scenario: Caret power notation
    When I run `olivia solve "x^2 - 5x + 6 = 0"`
    Then the output shows worked steps and "Answer: x = 2, x = 3"

  Scenario: Explicit multiplication
    When I run `olivia solve "2*x + 3 = 7"`
    Then the output shows worked steps and "Answer: x = 2"
```

### BS-005 — Interactive tutor mode (Socratic)

**Stories:** US-002

```gherkin
Feature: Interactive Socratic tutor

  Scenario: Tutor session with guiding questions
    Given Anthropic/Ollama backend is available
    When I run `olivia tutor "special relativity"`
    Then the agent asks a guiding question (does not lecture)
    And I can answer
    And the agent gives a hint or corrects misconception
    And session state persists across turns
    And I can exit gracefully with a summary
```

### BS-006 — Flashcard/worksheet/quiz generation from source documents

**Stories:** US-002

```gherkin
Feature: Study material generation from source

  Scenario: Flashcards from PDF
    Given a PDF file "paper.pdf" with content about Krebs cycle
    And LLM backend is available
    When I run `olivia study cards "Krebs cycle" --content-file paper.pdf -n 15`
    Then 15 cards are generated and saved to an SM-2 deck
    And each card's answer is grounded in the source (eval: answer_in_source ≥ 95%)

  Scenario: Worksheet from PDF
    When I run `olivia study worksheet "quadratic equations" --content-file paper.pdf -n 8`
    Then 8 problems + answer key are generated
    And content is grounded in the source

  Scenario: Interactive quiz from PDF
    When I run `olivia study quiz "Bayesian statistics" --content-file paper.pdf`
    Then an interactive quiz runs, grades answers, and shows results
```

### BS-007 — MCP co-working with Claude Code

**Stories:** US-003

```gherkin
Feature: MCP server exposes all 17 tools

  Scenario: All tools callable from Claude Code
    Given `olivia mcp-serve` is registered in Claude Code via .mcp.json
    When I invoke each tool from Claude
    Then all 17 tools execute and return results:
      | tool                      |
      | olivia_ask                |
      | olivia_solve              |
      | olivia_research           |
      | olivia_worksheet          |
      | molar_mass                |
      | balance_equation          |
      | convert_units             |
      | physical_constant         |
      | notebook_add              |
      | notebook_search           |
      | notebook_entries          |
      | meta_stats                |
      | ping                      |
    And round-trip: Claude asks → O.L.I.V.I.A. executes → result returned → Claude continues
```

### BS-008 — Code quality: mypy clean on core files

**Stories:** (technical hygiene)

```gherkin
Feature: Type checking

  Scenario: mypy passes on core modules
    When I run `mypy src/olivia`
    Then exit code is 0
    And no errors on core files (missing sympy/scipy stubs are ignored via config)
    Specifically fixed:
      | file                  | issue                              |
      | registry.py:70        | ToolRegistry.list type annotation  |
      | chemistry.py:210      | int * object operator              |
      | chemistry.py:301-302  | Fraction/int assignment + gcd arg  |
      | lab.py:60/69/82       | Sequence[str].append → list[str]   |
```

### BS-009 — Code quality: bandit no HIGH/MEDIUM

**Stories:** (technical hygiene)

```gherkin
Feature: Security linting

  Scenario: bandit finds no HIGH/MEDIUM issues
    When I run `bandit -r src/olivia`
    Then no HIGH or MEDIUM severity findings
    LOW findings acceptable for offline research agent
    Specifically addressed:
      | file               | issue                              | resolution                    |
      | literature.py      | XML parsing w/o defusedxml         | defusedxml.defuse_stdlib()    |
      | worksheet.py:83    | random (non-crypto)                | secrets or # nosec B311       |
      | science.py:386     | eval in sandboxed python_exec      | # nosec B307 with comment     |
      | science.py:415     | try/except/pass                    | log or handle                 |
      | science.py:418     | subprocess call                    | # nosec B603 with comment     |
```

### BS-010 — Ruff pre-commit hook installed

**Stories:** (technical hygiene)

```gherkin
Feature: Pre-commit linting

  Scenario: Ruff runs on commit in <2s
    Given .pre-commit-config.yaml with ruff check + ruff format hooks
    And `pre-commit install` has been run
    When I make a change and run `git commit`
    Then Ruff executes and completes in <2 seconds
    And commit proceeds if clean, blocks if not
```

## Implementation Decisions

1. **Backend configuration via `.env`** (T1): Follows O.L.I.V.I.A.'s existing `OLIVIA_` prefix convention with `__` for nesting. File is gitignored. No Hermes vault integration for this repo.

2. **Hybrid LLM strategy** (Q3=C): `OLIVIA_LLM__PROVIDER=auto` (default) with both Anthropic and Ollama configured. Routine tasks (solve, flashcards, simple research) → Ollama `llama3.1:8b`; deep research cycles → Anthropic. Benchmark `llama3.1:8b` first (Q6=D), then decide on adding `qwen2.5:14b`.

3. **Research cycle acceptance = full IMRaD with supported/refuted hypotheses** (Q9=F): This is the architecture's designed output. Anything less means the cycle isn't executing.

4. **Solver coverage focus on reach domains** (T3): Core domains (chemistry, math, physics, units at 100%) must not regress. Reach domains (currently 0–20%) are the improvement target.

5. **Equation parser extends existing sympy pipeline** (T4): Add system-of-equations detection before falling to LLM. Handle notation variants in the preprocessing layer (`safe_sympify`).

6. **MCP server is the integration surface** (Q4=None, US-003): O.L.I.V.I.A. remains a separate agent; MCP is the interoperability layer. No I.S.A.A.C. skill registration or shared memory in this spec.

7. **mypy/bandit in parallel with feature work** (Q10=B): These are independent hygiene tickets. Fix while working on T3/T4.

8. **Ruff pre-commit only** (Q5=A): Fast (<2s). Tests/eval/mypy stay in CI.

9. **Ollama model decision deferred** (Q6=D): Benchmark `llama3.1:8b` on actual O.L.I.V.I.A. tasks (T2, T5, T6) before pulling additional models.

10. **Anthropic key in local `.env`** (Q7=A): Simplest, follows project convention. Not in Hermes vault.

## Testing Decisions

- **External behavior only**: Tests verify CLI output, eval metrics, and MCP tool responses — not internal implementation.
- **Modules tested**:
  - `src/olivia/llm/client.py` — backend availability (BS-001)
  - `src/olivia/core/graph.py` — research cycle execution (BS-002)
  - `src/olivia/study/solver.py` + `tools/science.py` — solver/parser (BS-003, BS-004)
  - `src/olivia/study/tutor.py` — tutor mode (BS-005)
  - `src/olivia/study/flashcards.py`, `worksheet.py`, `quiz.py` — study generation (BS-006)
  - `src/olivia/mcp/server.py` — MCP tools (BS-007)
  - CI pipeline — mypy/bandit/ruff gates (BS-008, BS-009, BS-010)
- **Seam mapping**:
  - BS-001 → `olivia info` CLI
  - BS-002 → `olivia research --network` CLI
  - BS-003 → `olivia eval --check` CLI
  - BS-004 → `olivia solve` CLI
  - BS-005 → `olivia tutor` CLI (interactive)
  - BS-006 → `olivia study cards/worksheet/quiz --content-file` CLI
  - BS-007 → MCP tool calls from Claude Code
  - BS-008 → `mypy src/olivia` in CI
  - BS-009 → `bandit -r src/olivia` in CI
  - BS-010 → `pre-commit run` locally
- **Prior art**: Existing test suite (258 tests, all offline) in `tests/` covers unit behavior for all modules. Eval suites (`src/olivia/eval/`) define the metrics and gates. CI workflow (`.github/workflows/ci.yml`) runs lint + test matrix + eval on every PR.

## Out of Scope

- I.S.A.A.C. integration beyond MCP (no shared memory, no skill registration, no A2A fabric)
- Additional Ollama models beyond `llama3.1:8b` (decision deferred to post-benchmark)
- Commercial licensing (O.L.I.V.I.A. is CC BY-NC-SA 4.0)
- Web UI or desktop app — CLI + MCP only
- Distributed/deployed operation — local-first, single-user
- Literature retrieval backend swap (arXiv/Crossref/S2 are hardcoded)
- Multi-user or collaborative features

## Further Notes

- This spec was synthesized from a 2-round grilling session (Q1–Q10) with Matheus Soranço.
- The ticket order (T1→T2→T3/T4/T8/T9→T5/T6→T7→T10) reflects dependency graph and suggested 4-week execution.
- Each ticket should be created as a separate GitHub issue with `ready-for-agent` label, linked to this spec issue as parent (via GitHub sub-issues or `Part of #<this-issue>`).
- The `.env` file for T1 must be created locally — not committed. Add to `.gitignore` if not present.
- `ANTHROPIC_API_KEY` is required for T2, T5, T6, T7. If unavailable, those tickets block.
- Ollama must be running (`ollama serve`) with `llama3.1:8b` pulled for T1 verification.
- The eval gate (`olivia eval --check`) uses `src/olivia/eval/datasets/gates.json` for thresholds. Update it when T3 passes.
- Bandit LOW findings are accepted for this offline research agent; only HIGH/MEDIUM are blocking.
- Ruff version is pinned to 0.15.2 in `pyproject.toml` (per CI workflow) — pre-commit must use same version.