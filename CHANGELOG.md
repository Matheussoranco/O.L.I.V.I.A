# Changelog

All notable changes to O.L.I.V.I.A. are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
