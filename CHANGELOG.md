# Changelog

All notable changes to O.L.I.V.I.A. are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0-alpha]: https://github.com/matheussoranco/O.L.I.V.I.A/releases/tag/v0.1.0-alpha
