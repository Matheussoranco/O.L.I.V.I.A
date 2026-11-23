# Evidence Pack — O.L.I.V.I.A #15 (`T7: MCP Co-Working with Claude Code`)

- **Trace:** `olivia-15-t7`
- **Issue:** `Matheussoranco/O.L.I.V.I.A#15` (parent `#8`)
- **Author:** Gemini 4 Neon (High)
- **Branch / Worktree:** `feat/15-mcp-coworking` (`O.L.I.V.I.A-wt15`, branched from `origin/main` @ `c1d797c5d7f5850caf00f8ba11a285cf86b2494d`)
- **Verification Verdict:** **PASS** (offline automated test suite + live Claude Code `2.1.330` → `olivia mcp-serve` stdio MCP round-trip verified on candidate build)

---

## 1. Acceptance Criteria Mapping (Scoped by Verification Method)

| Criterion (`#15`) | Implementation | Verification Seam & Observed Evidence | Status |
|---|---|---|---|
| `olivia mcp-serve` registered in Claude Code via `.mcp.json` | Verified `.mcp.json` (`{"mcpServers":{"olivia":{"command":"olivia","args":["mcp-serve"]}}}`) | Automated check `test_mcp_json_registration_and_required_tools_catalog` **AND** live `claude -p --strict-mcp-config --mcp-config .mcp.json` discovered and launched `O.L.I.V.I.A-wt15\.venv\Scripts\olivia.exe mcp-serve` | **PASS** (live + automated) |
| Tool catalog & JSON-RPC `ping` (`olivia_ask`, `olivia_solve`, `olivia_research`, `olivia_worksheet`, `molar_mass`, `balance_equation`, `convert_units`, `physical_constant`, `notebook_add`, `notebook_search`, `notebook_entries`, `meta_stats`, `ping`, plus `olivia_study_plan`, `olivia_flashcards`, `olivia_quiz`, `olivia_lab`, `literature_search`, `python_exec`) | Added missing `notebook_entries` tool (`_notebook_entries(kind=None, limit=50)`) to `TOOLS` in `src/olivia/mcp/server.py` (18 MCP tools + JSON-RPC `ping`) | All 18 tools + `ping` catalog/handlers verified in unit & subprocess stdio JSON-RPC harness (`test_mcp_json_registration_and_required_tools_catalog`, `test_notebook_add_entries_and_search`, `test_ping_and_notifications`); 4 representative tools (`molar_mass`, `convert_units`, `notebook_add`, `notebook_entries`) additionally exercised through live Claude Code | **PASS** (catalog automated; 4 tools live) |
| Offline subprocess stdio JSON-RPC harness | Local simulated JSON-RPC client spawning `python -m olivia mcp-serve` over stdin/stdout | `test_subprocess_mcp_serve_roundtrip` (`initialize`, `notifications/initialized`, `ping`, `tools/list`, `molar_mass`, `convert_units`, `notebook_add`, `notebook_entries`) | **PASS** (automated harness) |
| Live Claude-to-O.L.I.V.I.A. round-trip (`Claude asks → O.L.I.V.I.A. executes → result returned → Claude continues`) | Repository `.mcp.json` with candidate `O.L.I.V.I.A-wt15\.venv\Scripts\olivia.exe` on `PATH` | Live `claude -p ... --strict-mcp-config --mcp-config .mcp.json --allowedTools "mcp__olivia__*" --output-format json --no-session-persistence` (`Claude Code 2.1.330`, `claude-sonnet-5-5`, `session_id=721cc990-87f2-4e76-b400-bd70d79d9232`, `num_turns=6`, `is_error=false`, `permission_denials=[]`) | **PASS** (live Claude Code round-trip) |

---

## 2. Live Claude Code Round-Trip Observed Transcript Summary

- **Command executed (2026-11-23):**
  ```powershell
  $env:PATH = "C:\Users\mathe\Documents\Code\O.L.I.V.I.A-wt15\.venv\Scripts;" + $env:PATH
  claude -p "Use the olivia MCP tools (do not use Bash or local files): 1) call molar_mass for H2SO4, 2) call convert_units to convert 100 km/h to m/s, 3) call notebook_add ..., 4) call notebook_entries to read back the saved entry." `
    --strict-mcp-config --mcp-config "C:\Users\mathe\Documents\Code\O.L.I.V.I.A-wt15\.mcp.json" `
    --allowedTools "mcp__olivia__*" --output-format json --no-session-persistence
  ```
- **Observed live results returned to and summarized by Claude Code (`session_id=721cc990-87f2-4e76-b400-bd70d79d9232`, `num_turns=6`, `is_error=false`):**
  1. `mcp__olivia__molar_mass("H2SO4")` → `98.072 g/mol` (H: 2.06%, S: 32.69%, O: 65.25%).
  2. `mcp__olivia__convert_units(100, "km/h", "m/s")` → `27.77777777777778 m/s`.
  3. `mcp__olivia__notebook_add(kind="note", ...)` → saved entry `note_ecbd7d48` at `2026-11-23T09:51:52` (independently corroborated on disk in `~/.olivia/notebook.json`, then cleaned up afterward so user notebook state was not polluted).
  4. `mcp__olivia__notebook_entries(kind="note")` → returned entry `note_ecbd7d48` cleanly.
- **Scope note:** The remaining 14 tools (including LLM-backed tools such as `olivia_ask`/`olivia_research` when an LLM provider is configured) were verified via unit tests and the local subprocess stdio JSON-RPC harness rather than individually invoked in the live Claude session.

---

## 3. Automated Checks Executed

- `uv run --python 3.12 --extra dev --extra science ruff check src tests` — `All checks passed!`
- `uv run --python 3.12 --extra dev --extra science ruff format --check src tests` — `90 files already formatted`
- `uv run --python 3.12 --extra dev --extra science mypy src/olivia` — `Success: no issues found in 65 source files`
- `uv run --python 3.12 --extra dev --extra science pytest tests/ -q` — `379 passed, 2 skipped`
- `uv run --python 3.12 --extra dev --extra science olivia eval --check` — `All gates hold.`
