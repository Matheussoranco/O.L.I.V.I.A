# O.L.I.V.I.A.

[![License: AGPL-3.0-only](https://img.shields.io/badge/License-AGPL--3.0--only-blue.svg)](LICENSE)

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
   **offline**: outbound literature/page requests are disabled by default.
   Every LLM consumer has a deterministic symbolic fallback.
4. **Quantitative care** — effect sizes and uncertainty, not just p-values.

## Install

```bash
pip install -e .            # lean core (httpx, pydantic, typer, rich, defusedxml)
pip install -e ".[all]"     # + anthropic, langgraph, numpy/scipy/sympy, pymupdf, bs4
```

Configure via environment or a local `.env` file (`OLIVIA_` prefix, `__` for nesting):

```bash
OLIVIA_LLM__PROVIDER=anthropic   # or: ollama | none | auto (default)
OLIVIA_LLM__MODEL=claude-opus-4-8
OLIVIA_LLM__OLLAMA_MODEL=llama3.1:8b
ANTHROPIC_API_KEY=sk-ant-...     # OLIVIA_ANTHROPIC_API_KEY also supported
```

## CLI

```bash
olivia ask "Why is the sky blue?"                 # Mixture-of-Experts answer
olivia solve "solve x**2 - 5x + 6 = 0 for x"      # GPAI-style worked solution
olivia solve "the system 2x + y = 10 and x - y = 2"  # systems, with elimination steps
olivia solve "molar mass of C6H12O6"              # chemistry, physics, units too
olivia research "Does spaced repetition beat massed practice?"
olivia research "Does spaced repetition beat massed practice?" --network
olivia academic "Review this manuscript's methods and citations"
olivia study plan "Linear algebra" --weeks 6
olivia study cards "Krebs cycle" -n 15            # flashcards → SM-2 deck
olivia study quiz "Bayesian statistics"
olivia study worksheet "quadratic equations" -n 8 # practice set + answer key
olivia study review "Krebs cycle"                 # spaced-repetition session
olivia tutor "special relativity"                 # Socratic tutor (/hint, /summary, /exit)
olivia lab "What limits perovskite solar cell stability?"   # multi-agent seminar
olivia mcp-serve                                  # MCP stdio server for Claude
olivia eval --check                               # offline evaluation gates
olivia info                                       # backend/config status
```

### Network requests and privacy

Network access is off unless you pass `--network` or set
`OLIVIA_NETWORK_ENABLED=true`. Requests to literature services identify only the
agent. Crossref gives better rate limits to clients that name a contact; if you
want that, set `OLIVIA_CONTACT_EMAIL` (environment or `.env`) and only then is
your address added to the `User-Agent`.

### Step-by-step STEM solving

`olivia solve` (and the `science` expert behind `olivia ask`) is **symbolic-first**
and works with no LLM backend:

- **Maths** (sympy) — solve/factor/expand/simplify equations, differentiate,
  integrate, evaluate, with pre-evaluation AST bounds against explosive powers.
  Equations are read as people write them: systems of any size separated by
  `,` `;` `and` or new lines (`solve for x and y: …`, `the system …`), caret or
  Unicode powers (`x^2`, `x²`), `−` `×` `÷` `√` `π`, explicit or implicit
  multiplication, and indexed unknowns (`x1`). Square linear systems show
  Gaussian elimination; quadratics show the discriminant; every answer is
  checked by substitution. Text with words in it (`the value 2x = 4`) is never
  "solved" as a product of letters — it abstains instead.
- **Chemistry** — molar mass from a 118-element table (groups & hydrates),
  equation balancing by exact conservation of atoms (`2 H2 + O2 → 2 H2O`),
  percent composition, IUPAC oxidation states, mass ↔ moles conversions, and
  complete combustion stoichiometry.
- **Physics** — CODATA constant lookup (`speed of light`, `Planck constant`,
  `N_A`), constant-acceleration kinematics (including deceleration), free fall,
  kinetic energy, Newton's second law, photon energy–wavelength–frequency, and
  simple pendulum period.
- **Units** — SI/imperial/temperature conversion (including full English unit
  names and plurals) and dimensional analysis (`60 mph → 26.82 m/s`;
  `N → kg·m·s⁻², force`).

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
│                (restricted python_exec, guarded safe_sympify, Welch t-test, power)
│                units.py (dimensional analysis) · chemistry.py (molar mass,
│                balancing, oxidation states) · physics.py (CODATA constants)
├── research/    literature → hypothesis → experiment → analysis → critic → report
├── study/       srs.py (SM-2 decks) · flashcards · quiz · planner · tutor
│                solver.py · chemistry_solver.py · physics_solver.py · worksheet.py
├── experts/     Mixture-of-Experts: math, stats, science, code, literature,
│                general + router
├── agents/      Hermes-style role-typed sub-agents (researcher, critic,
│                experimenter, writer, tutor) · AgentPool · ResearchLab
├── meta/        MetaLearner (SQLite) — strategy win-rates feed expert routing
├── memory/      notebook.py — append-only lab notebook
├── eval/        Offline research, study, and symbolic evaluation suites & gates
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
stdio (**19 tools**: `olivia_ask`, `olivia_solve`, `olivia_research`,
`olivia_worksheet`, `olivia_study_plan`, `olivia_flashcards`, `olivia_quiz`,
`olivia_lab`, `molar_mass`, `balance_equation`, `convert_units`,
`physical_constant`, `literature_search`, `python_exec`, `notebook_add`,
`notebook_search`, `notebook_entries`, `meta_stats`, and `ping`, plus the
JSON-RPC `ping` method). Register with the provided `.mcp.json` or:

```json
{"mcpServers": {"olivia": {"command": "olivia", "args": ["mcp-serve"]}}}
```

### Academic Research Suite integration

O.L.I.V.I.A. vendors the ARS-Codex router under
[`skills/academic-research-suite`](skills/academic-research-suite) and exposes
the native route inspector as `olivia academic`. It resolves research,
paper-writing, peer-review, end-to-end pipeline, and experiment requests to
the corresponding `WORKFLOW.md` recipe. The same snapshot is available as a
local Codex plugin under [`plugins/ars-codex`](plugins/ars-codex), registered by
the local marketplace at
[`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json).

The global Codex installation is also available after installing the skill
from GitHub; restart or refresh the Codex session if its skill inventory was
already loaded. `olivia academic` reads the vendored directory, so it requires
a source checkout; the wheel ships only the `olivia` package.

## Tests & Evaluation

```bash
python -m pytest -q        # fully offline by default
olivia eval --check        # verify research, study, and symbolic eval gates
```

## Status

**0.4.0 — Alpha.** See [CHANGELOG.md](CHANGELOG.md). The API and CLI may still
change; the offline-first contract will not.

## License

Original project code is licensed under the [GNU Affero General Public License v3.0 only](LICENSE) (`AGPL-3.0-only`).

Copyright (c) 2025–2026 Matheus Pullig Soranço de Carvalho (Matheus Soranço).

The AGPL permits commercial and noncommercial use. If you modify the program and let users interact with that version remotely through a network, offer them its corresponding source under the AGPL. Distribution is subject to the license’s corresponding-source and notice requirements.

The separately licensed material under [`skills/academic-research-suite/`](skills/academic-research-suite/) and upstream material in [`patches/`](patches/) retain their applicable terms. See the [upstream notices](skills/academic-research-suite/ars/NOTICE.md).

Previously published versions retain their original terms. The previous [license text](LICENSES/Apache-2.0.previous.txt) is retained for reference.
