# Evidence Pack — O.L.I.V.I.A #15 (`T7: MCP Co-Working with Claude Code`)

- **Trace:** `olivia-15-t7`
- **Issue:** `Matheussoranco/O.L.I.V.I.A#15` (parent `#8`)
- **Author:** Gemini 4 Neon (High)
- **Branch / Worktree:** `feat/15-mcp-coworking` (`O.L.I.V.I.A-wt15`, branched from `origin/main` @ `c1d797c5d7f5850caf00f8ba11a285cf86b2494d`)
- **Verification Verdict:** **PARTIAL LIVE / FULL AUTOMATED PASS** (18 MCP tools discovered in catalog; 4 tools invoked in local subprocess harness; 4 tools invoked in live Claude Code `2.1.330` session; `ping` verified as MCP JSON-RPC protocol method, not as an exposed `tools/list` tool)

---

## 1. Explicit Tool & Protocol Coverage Matrix

| Surface / Tool | Catalog (`tools/list` / unit tests) | Subprocess Stdio Harness (`test_subprocess_mcp_serve_roundtrip`) | Live Claude Code `2.1.330` (`session_id=721cc990`) | Notes |
|---|---|---|---|---|
| `.mcp.json` registration (`olivia mcp-serve`) | Verified (`test_mcp_json_registration_and_required_tools_catalog`) | Spawned `python -m olivia mcp-serve` | Launched `.venv\Scripts\olivia.exe mcp-serve` via `--strict-mcp-config --mcp-config .mcp.json` | Live discovery confirmed |
| JSON-RPC `initialize` / `notifications/initialized` / `tools/list` | Verified | **Invoked** | **Invoked** (by Claude Code MCP client) | Protocol handshake |
| JSON-RPC `ping` (`method: "ping"` → `{}`) | Verified (`test_ping_and_notifications`) | **Invoked** (as JSON-RPC method) | **Not invoked as a Claude tool** | **Scope clarification below** |
| `molar_mass` | Discovered + unit-tested | **Invoked** | **Invoked live** (`H2SO4` → `98.072 g/mol`) | Full end-to-end |
| `convert_units` | Discovered + unit-tested | **Invoked** | **Invoked live** (`100 km/h` → `27.7778 m/s`) | Full end-to-end |
| `notebook_add` | Discovered + unit-tested | **Invoked** | **Invoked live** (saved `note_ecbd7d48`) | Full end-to-end |
| `notebook_entries` *(added in this PR)* | Discovered + unit-tested | **Invoked** | **Invoked live** (read back `note_ecbd7d48`) | Full end-to-end |
| `olivia_ask`, `olivia_solve`, `olivia_research`, `olivia_worksheet`, `balance_equation`, `physical_constant`, `notebook_search`, `meta_stats`, `olivia_study_plan`, `olivia_flashcards`, `olivia_quiz`, `olivia_lab`, `literature_search`, `python_exec` (14 tools) | **Discovered in `tools/list` + unit-tested** (`tests/test_mcp/test_server.py`) | Discovered via `tools/list` (not individually invoked in subprocess test) | Discovered by Claude Code MCP client (not individually invoked in the 4-call live session) | Catalog & handler verified; live per-tool invocation not claimed |

### Explicit Clarification on `ping` (Protocol Method vs. Callable Tool)

- Per the Model Context Protocol specification (`2024-11-05`), `ping` is a **standard JSON-RPC 2.0 utility request method** (`{"jsonrpc": "2.0", "id": ..., "method": "ping"}` returning `{}`), **not** an item in `tools/list`.
- `src/olivia/mcp/server.py` implements `ping` as a JSON-RPC 2.0 protocol method (`_handle()` line 422), verified in both unit tests and the subprocess stdio harness.
- **Explicit gap if `#15` requires a model-callable `ping` tool:** `ping` is **not** registered in `TOOLS` (`tools/list`) and is therefore **not** exposed to Claude as `mcp__olivia__ping`. Keeping `ping` at the JSON-RPC protocol layer follows the MCP specification and avoids duplicating protocol health-checks as model-facing tools; if acceptance requires an explicit `tools/list` `ping` tool in addition to JSON-RPC `ping`, that must be added separately or `#15` acceptance wording updated accordingly.

---

## 2. Live Claude Code Round-Trip Observed Transcript Summary

- **Command executed (`2026-11-23`):**
  ```powershell
  $env:PATH = "C:\Users\mathe\Documents\Code\O.L.I.V.I.A-wt15\.venv\Scripts;" + $env:PATH
  claude -p "Use the olivia MCP tools (do not use Bash or local files): 1) call molar_mass for H2SO4, 2) call convert_units to convert 100 km/h to m/s, 3) call notebook_add ..., 4) call notebook_entries to read back the saved entry." `
    --strict-mcp-config --mcp-config "C:\Users\mathe\Documents\Code\O.L.I.V.I.A-wt15\.mcp.json" `
    --allowedTools "mcp__olivia__*" --output-format json --no-session-persistence
  ```
- **Observed live results (`Claude Code 2.1.330`, `claude-sonnet-5-5`, `session_id=721cc990-87f2-4e76-b400-bd70d79d9232`, `num_turns=6`, `is_error=false`, `permission_denials=[]`):**
  1. `mcp__olivia__molar_mass("H2SO4")` → `98.072 g/mol` (H: 2.06%, S: 32.69%, O: 65.25%).
  2. `mcp__olivia__convert_units(100, "km/h", "m/s")` → `27.77777777777778 m/s`.
  3. `mcp__olivia__notebook_add(kind="note", ...)` → saved entry `note_ecbd7d48` at `2026-11-23T09:51:52` (corroborated on disk in `~/.olivia/notebook.json`, then cleaned up afterward so user notebook state was not polluted).
  4. `mcp__olivia__notebook_entries(kind="note")` → returned entry `note_ecbd7d48` cleanly.

---

## 3. Automated Checks Executed

- `uv run --python 3.12 --extra dev --extra science ruff check src tests` — `All checks passed!`
- `uv run --python 3.12 --extra dev --extra science ruff format --check src tests` — `90 files already formatted`
- `uv run --python 3.12 --extra dev --extra science mypy src/olivia` — `Success: no issues found in 65 source files`
- `uv run --python 3.12 --extra dev --extra science pytest tests/ -q` — `379 passed, 2 skipped` (incl. 22 tests in `tests/test_mcp/test_server.py`)
- `uv run --python 3.12 --extra dev --extra science olivia eval --check` — `All gates hold.`
