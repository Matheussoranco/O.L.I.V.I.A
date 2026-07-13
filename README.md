# O.L.I.V.I.A.

**Open Learning Intelligence & Virtual Investigation Assistant** — an AI agent
specialised in study, learning, and scientific research and discovery.

## Lineage

| Inspiration | What OLIVIA takes from it |
|---|---|
| **I.S.A.A.C.** | Cognitive graph cycle, Mixture-of-Experts routing, meta-learning from task outcomes, MCP co-working with Claude |
| **Nous Research Hermes** | Model-agnostic `<tool_call>` function-calling protocol, so any LLM (local Ollama models included) can drive the agent loop; `<think>` reasoning traces |
| **Claude for Science** | The scientific workflow as a first-class loop: literature review → hypothesis → experiment design → analysis → Popperian critique → scientific writing |

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
olivia research "Does spaced repetition beat massed practice?"
olivia study plan "Linear algebra" --weeks 6
olivia study cards "Krebs cycle" -n 15            # flashcards → SM-2 deck
olivia study quiz "Bayesian statistics"
olivia study review "Krebs cycle"                 # spaced-repetition session
olivia tutor "special relativity"                 # Socratic tutor (interactive)
olivia lab "What limits perovskite solar cell stability?"   # multi-agent seminar
olivia mcp-serve                                  # MCP stdio server for Claude
olivia info                                       # backend/config status
```

## Architecture

```
src/olivia/
├── core/        records.py (Paper, Hypothesis, ExperimentPlan, …)
│                state.py (OliviaState) · graph.py (cognitive cycle)
├── llm/         client.py (Anthropic | Ollama | Null) · hermes.py (tool-calling loop)
│                prompts.py · structured.py (tolerant JSON extraction)
├── tools/       registry.py · literature.py (arXiv/Crossref/S2) · science.py
│                (sandboxed python_exec, sympy, Welch t-test, power analysis)
├── research/    literature → hypothesis → experiment → analysis → critic → report
├── study/       srs.py (SM-2 decks) · flashcards · quiz · planner · tutor
├── experts/     Mixture-of-Experts: math, stats, code, literature, general + router
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
stdio. Register with the provided `.mcp.json` or:

```json
{"mcpServers": {"olivia": {"command": "olivia", "args": ["mcp-serve"]}}}
```

## Tests

```bash
python -m pytest -q     # fully offline: no keys, no network
```

## License

AGPL-3.0-or-later
