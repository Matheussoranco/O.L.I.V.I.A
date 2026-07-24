# O.L.I.V.I.A.

**Open Learning Intelligence & Virtual Investigation Assistant** — an AI agent
specialised in study, learning, and scientific research and discovery.

## Lineage

| Inspiration | What OLIVIA takes from it |
|---|---|
| **I.S.A.A.C.** | Cognitive graph cycle, Mixture-of-Experts routing, meta-learning from task outcomes, MCP co-working with Claude |
| **Nous Research Hermes** | Model-agnostic `<tool_call>` function-calling protocol, so any LLM (local Ollama models included) can drive the agent loop; `<think>` reasoning traces |
| **Claude for Science** | The scientific workflow as a first-class loop: literature review → hypothesis → experiment design → analysis → Popperian critique → scientific writing; hard-science tooling (units, chemistry, physics) |
| **GPAI (STEM)** | Step-by-step worked solutions and practice worksheets — the work, not just the answer — solved symbolically wherever possible |

## Design principles

1. **Epistemic honesty** — established vs. hypothesised vs. unknown is always
   distinguished; sources cited when available, absence stated when not.
2. **Popperian rigour** — every hypothesis carries explicit predictions and a
   concrete falsification test; unfalsifiable hypotheses are rejected.
3. **Graceful degradation** — the whole system imports, runs, and tests
   **offline**: no API keys, no network. Every LLM consumer has a
   deterministic symbolic fallback.
4. **Quantitative care** — effect sizes and uncertainty, not just p-values.

## Install

```bash
pip install -e .            # lean core (httpx, pydantic, typer, rich)
pip install -e ".[all]"     # + anthropic, langgraph, numpy/scipy/sympy, pymupdf, bs4
```

Configure via environment (`OLIVIA_` prefix, `__` for nesting):

```bash
OLIVIA_LLM__PROVIDER=anthropic   # or: ollama | none | auto (default)
OLIVIA_LLM__MODEL=claude-opus-4-8
OLIVIA_LLM__OLLAMA_MODEL=llama3.1:8b
ANTHROPIC_API_KEY=sk-ant-...
```

## CLI

```bash
olivia ask "Why is the sky blue?"                 # Mixture-of-Experts answer
olivia solve "solve x**2 - 5x + 6 = 0 for x"      # GPAI-style worked solution
olivia solve "molar mass of C6H12O6"              # chemistry, physics, units too
olivia research "Does spaced repetition beat massed practice?"
olivia study plan "Linear algebra" --weeks 6
olivia study cards "Krebs cycle" -n 15            # flashcards → SM-2 deck
olivia study quiz "Bayesian statistics"
olivia study worksheet "quadratic equations" -n 8 # practice set + answer key
olivia study review "Krebs cycle"                 # spaced-repetition session
olivia tutor "special relativity"                 # Socratic tutor (interactive)
olivia lab "What limits perovskite solar cell stability?"   # multi-agent seminar
olivia mcp-serve                                  # MCP stdio server for Claude
olivia info                                       # backend/config status
```

### Step-by-step STEM solving

`olivia solve` (and the `science` expert behind `olivia ask`) is **symbolic-first**
and works with no LLM backend:

- **Maths** (sympy) — solve/factor equations, differentiate, integrate, evaluate.
- **Chemistry** — molar mass from a 118-element table (groups & hydrates), and
  equation balancing by exact conservation of atoms (`H2 + O2 → 2 H2O ... 2 H2 + O2`).
- **Physics** — CODATA constant lookup (`speed of light`, `Planck constant`, `N_A`).
- **Units** — SI/imperial/temperature conversion and dimensional analysis
  (`60 mph → 26.82 m/s`; `N → kg·m·s⁻², force`).

When nothing symbolic fits and an LLM is configured, it produces structured steps;
with no backend it says so plainly rather than inventing an answer.

## Architecture

```
src/olivia/
├── core/        records.py (Paper, Hypothesis, ExperimentPlan, …)
│                state.py (OliviaState) · graph.py (cognitive cycle)
├── llm/         client.py (Anthropic | Ollama | Null) · hermes.py (tool-calling loop)
│                prompts.py · structured.py (tolerant JSON extraction)
├── tools/       registry.py · literature.py (arXiv/Crossref/S2) · science.py
│                (sandboxed python_exec, sympy, Welch t-test, power analysis)
│                units.py (dimensional analysis) · chemistry.py (molar mass,
│                balancing) · physics.py (CODATA constants)
├── research/    literature → hypothesis → experiment → analysis → critic → report
├── study/       srs.py (SM-2 decks) · flashcards · quiz · planner · tutor
│                solver.py (step-by-step WorkedSolution) · worksheet.py
├── experts/     Mixture-of-Experts: math, stats, science, code, literature,
│                general + router
├── agents/      Hermes-style role-typed sub-agents (researcher, critic,
│                experimenter, writer, tutor) · AgentPool · ResearchLab
├── meta/        MetaLearner (SQLite) — strategy win-rates feed expert routing
├── memory/      notebook.py — append-only lab notebook
└── mcp/         JSON-RPC 2.0 stdio server (Claude co-working)
```

### The research cycle

```
question ─► literature review ─► hypotheses (falsifiable by construction)
        ─► experiment design (variables, power analysis, simulation code)
        ─► analysis (sandboxed execution, effect size + p-value)
        ─► Popperian critique ──► revise hypotheses ─┐
        ─► DiscoveryReport (IMRaD markdown) ◄────────┘  (≤ max_revisions loops)
```

### MCP co-working

`olivia mcp-serve` exposes the agent to Claude Code / Claude Desktop over
stdio (17 tools: `olivia_ask`, `olivia_solve`, `olivia_research`,
`olivia_worksheet`, `molar_mass`, `balance_equation`, `convert_units`,
`physical_constant`, `notebook_*`, …). Register with the provided `.mcp.json` or:

```json
{"mcpServers": {"olivia": {"command": "olivia", "args": ["mcp-serve"]}}}
```

## Tests

```bash
python -m pytest -q     # 166 tests, fully offline: no keys, no network
```

## Status

**0.1.0 — Alpha.** See [CHANGELOG.md](CHANGELOG.md). The API and CLI may still
change; the offline-first contract will not.

## License

[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)
— see [LICENSE](LICENSE). Noncommercial use only: you may use, modify, and share
OLIVIA for any purpose except a commercial one. Two conditions come with that:
keep the attribution, and license anything you share onward — including modified
versions — under these same terms (**ShareAlike**, i.e. copyleft). Commercial use
requires separate written permission.
