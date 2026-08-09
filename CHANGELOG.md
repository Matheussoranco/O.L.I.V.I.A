# Changelog

All notable changes to O.L.I.V.I.A. are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-08-09 — The evaluation harness, and the first honest baseline

O.L.I.V.I.A. had never been benchmarked. 0.3.0 builds the harness, runs it, and
records what came back — including the parts that are bad. Nothing was fixed in
response to its own measurements; each failure became a roadmap exit criterion
instead, so this baseline describes the code as it stood rather than as the eval
prompted it to become.

### Added

- **Three held-out eval suites**, with explicit chance baselines.
  - *Symbolic solving* — 64 cases (39 `core`, 25 `reach`) across maths, chemistry,
    physics and units, scoring the symbolic-first path and the LLM fallback
    **separately**, so a regression in the former cannot hide behind the latter.
  - *Research-cycle critique* — 27 cases: 19 deliberately flawed across 6 families
    plus **8 sound controls**, scoring catch rate *and* false-alarm rate. A critic
    that rejects everything is not a good critic.
  - *Study tools* — 104 items: 24 SM-2 sequences (157 reviews) replayed against an
    independent reference implementation, 20 grading cases, and 6 source passages
    yielding 36 flashcards and 36 quiz questions.
- **`olivia eval`**, with `--check` gating on measured floors *and* ceilings.
- `tests/test_eval/` asserts the datasets' own honesty rules, so the eval cannot be
  softened one commit at a time.

### Measured — the 0.3.0 baseline

| suite | result |
|---|---|
| Symbolic solving | **62.5%** overall — core 39/39 (100%), reach 1/25 (4%) |
| | precision 97.6%, abstain 35.9%, **wrong_rate 1.6%** |
| Critique | **26.3%** catch (5/19), **0.0%** false alarm (0/8), Youden's J 0.263 |
| SM-2 | **98.7%** step-exact (155/157), **lapse branch 100%** (39/39) |
| Grading | 100% (20/20) |
| Flashcard fidelity | 100% on all four checks |
| Offline quiz | **0/36** |

Three findings worth stating plainly:

- **The Popperian critique is a schema validator.** It catches
  `unfalsifiable_structural` 3/3 and `overfit_n1_structural` 2/2, and **0/4
  circular, 0/4 contradicted-by-own-evidence, 0/4 semantically unfalsifiable,
  0/2 overgeneralised-from-n=1**. It catches exactly what it was coded for and
  nothing requiring semantic judgement. The 0% false-alarm rate is genuine, not
  the artefact of a critic that never fires — the structural families prove it fires.
- **Offline quiz generation is broken.** Every question contains its own answer
  verbatim, because the prompt quotes the source sentence and `answer_text` *is*
  that sentence.
- **`d/dx of e^x` returns `e**x*f*o*log(e)` at `confidence=0.9`** — implicit
  multiplication parses the English word "of" as `o*f`. Confidently wrong, which
  is worse than the abstention the solver manages elsewhere.

The 2/157 SM-2 divergence is banker's rounding: `425 × 1.3 = 552.5 → 552`, where
half-up gives 553.

### Fixed

- **`_load_suites()` could silently skip whole eval suites.** It guarded its lazy
  imports with `if _REGISTRY: return`, treating "non-empty" as "loaded" — so any
  module importing one suite prevented the other two from ever loading. The visible
  symptom was a `KeyError` on `--suite study`; the dangerous one was silent, with
  `run_all()` scoring only whatever happened to be imported and publishing it as a
  full run. A green "all gates hold" while two thirds of the eval never executed.
  Caught by the harness's own tests on their first run.

### CI

- **`CI / eval`** runs on every push and PR with no key required; `--check` exits
  non-zero only on a breached gate.
- **`Eval (LLM paths)`** runs weekly and on demand, never on a PR. A preflight job
  probes for `ANTHROPIC_API_KEY` and passes the answer down, because secrets cannot
  be read in a job-level `if:`. With no secret the workflow **ends green** with a
  "skipped, not failed" note.

### Docs

- `docs/ROADMAP-1.0.md`, following the I.S.A.A.C. pattern: every version-line claim
  gated behind a measured number rather than an adjective.

## [0.2.0] — 2026-07-27

A licensing and toolchain release. **No behavioural change** — the only code
touched since `0.1.0-alpha` was reformatted by `ruff format`, and the suite is
byte-for-byte the same 166 offline tests.

The minor bump reflects the licence change, not new features. SemVer governs the
public API and says nothing about licensing, but the terms you may use O.L.I.V.I.A.
under have changed materially, and that is not a patch.

### Changed

- **Relicensed from AGPL-3.0-or-later to
  [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).** Read
  this before upgrading — it is a *trade*, not a tightening:
  - **Commercial use is now prohibited** without separate written permission.
    AGPL-3.0 permitted it, subject to copyleft. If you were relying on that, stay
    on `0.1.0-alpha`: **a licence already granted cannot be retroactively
    revoked**, so anyone who received an earlier commit keeps their AGPL rights
    to that version.
  - **Copyleft is retained** via ShareAlike (§3(b)): anything you share onward,
    modified or not, must carry these same terms.
  - **No patent or trademark grant** (§2(b)(2)). This is the one place the new
    licence is genuinely weaker than AGPL-3.0.
  - GitHub reports this repository as `NOASSERTION`. That is expected and
    unfixable: its detector only recognises the licences on choosealicense.com,
    whose sole Creative Commons entry is CC0-1.0, so every NonCommercial licence
    is excluded by design. The README badge exists to compensate.
- `LICENSE` now holds the **verbatim** canonical CC BY-NC-SA 4.0 legal text and
  nothing else; the copyright line, SPDX identifier and plain-language summary
  live in the README, which is where §3(a)(1) attribution expects them.
- Whole tree normalised with `ruff format`.

### Added

- **CI** (`.github/workflows/ci.yml`) — `ruff check`, `ruff format --check`, and
  the full offline suite on Python 3.10 / 3.11 / 3.12.
- `ruff` is **pinned exactly** (`ruff==0.15.2`) in the dev extra rather than
  floated. An unpinned `ruff>=0.4` is a time bomb: ruff 0.16.0 widened its
  built-in default rule set and
  turned green pipelines red across sibling projects with no source change.
  The lint configuration selects its rules explicitly for the same reason.

## [0.1.0-alpha] — 2026-07-20

First public alpha. The whole system imports, runs, and tests **fully offline**
— no API keys, no network — with a deterministic symbolic fallback behind every
LLM consumer.

### Added — core agent

- **Cognitive cycle** (`core/graph.py`) with three modes: `ask`, `research`,
  `study`. Sequential pipeline is authoritative; compiles to a LangGraph
  `StateGraph` when `langgraph` is installed.
- **LLM layer** (`llm/`) — Anthropic / Ollama / Null backends behind a single
  `LLMClient`, resolved by tier (`default`/`fast`/`strong`); Hermes-style
  `<tool_call>` loop; tolerant JSON extraction.
- **Research cycle** (`research/`) — literature review → falsifiable hypotheses
  → powered experiment design → sandboxed analysis → Popperian critique →
  revision → IMRaD report. Sample sizes come from a symbolic power analysis,
  never the model.
- **Mixture-of-Experts** (`experts/`) — math, stats, science, code, literature,
  general; hybrid router blends `0.7·symbolic + 0.3·MetaLearner win-rate`.
- **Study tools** (`study/`) — SM-2 spaced repetition, flashcards, quizzes,
  study planner, Socratic tutor.
- **Agents** (`agents/`) — role-typed Hermes sub-agents, `AgentPool`,
  `ResearchLab` seminar (researcher → critic → writer).
- **MetaLearner** (`meta/`) — SQLite outcome ledger with Laplace-smoothed
  win-rates feeding expert routing.
- **Lab notebook** (`memory/`) — append-only JSON with keyword search.
- **MCP server** (`mcp/`) — zero-dependency JSON-RPC 2.0 stdio server for
  Claude Code / Claude Desktop co-working.
- **CLI** — `olivia ask | research | solve | study … | tutor | lab | mcp-serve
  | info` (typer + rich).

### Added — STEM / hard-science layer (GPAI + Claude-for-Science)

- **Step-by-step solver** (`study/solver.py`) — `solve_problem` returns a
  `WorkedSolution` (ordered steps + final answer + method). Symbolic-first:
  sympy for maths, the chemistry/physics/units tools for the sciences, a
  structured-JSON LLM fallback, and an honest "cannot solve offline" otherwise.
- **Practice worksheets** (`study/worksheet.py`) — problem sets with a
  worked-solution answer key; a seeded offline generator emits randomised maths
  problems (linear, quadratic, derivative, arithmetic).
- **Units tool** (`tools/units.py`) — SI/imperial/temperature conversion and
  dimensional analysis over the seven SI base dimensions, with metric prefixes.
- **Chemistry tool** (`tools/chemistry.py`) — 118-element periodic table, a
  formula parser (nested groups and hydrates), molar mass, and equation
  balancing by exact rational nullspace (conservation of atoms).
- **Physics tool** (`tools/physics.py`) — CODATA physical constants with
  natural-language, case-sensitive lookup (`G` ≠ `g`).
- **Science expert** (`experts/science_expert.py`) — routes STEM questions
  through the deterministic solver before any LLM.
- **New CLI** — `olivia solve` and `olivia study worksheet`.
- **New MCP tools** — `olivia_solve`, `olivia_worksheet`, `molar_mass`,
  `balance_equation`, `convert_units`, `physical_constant` (server now exposes
  17 tools).

### Quality

- 166 tests, all passing offline (network access is blocked in the test
  fixtures; the LLM provider is forced to `none`).
- `ruff check src tests` clean (target py310, line length 100).

[0.2.0]: https://github.com/matheussoranco/O.L.I.V.I.A/releases/tag/v0.2.0
[0.1.0-alpha]: https://github.com/matheussoranco/O.L.I.V.I.A/releases/tag/v0.1.0-alpha
