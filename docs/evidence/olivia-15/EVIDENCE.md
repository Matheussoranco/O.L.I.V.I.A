# Evidence Pack — O.L.I.V.I.A #15 (`T7: MCP Co-Working with Claude Code`)

- **Trace:** `olivia-15-t7`
- **Issue:** `Matheussoranco/O.L.I.V.I.A#15` (parent `#8`)
- **Author:** Gemini 4 Neon (High)
- **Branch / Worktree:** `feat/15-mcp-coworking` (`O.L.I.V.I.A-wt15`, branched from `origin/main` @ `c1d797c5d7f5850caf00f8ba11a285cf86b2494d`)
- **Verification Verdict:** **PASS** (19 MCP tools incl. `notebook_entries` & callable `ping` discovered in `tools/list`; 5 tools + JSON-RPC protocol `ping` invoked in local subprocess harness; 5 tools incl. `mcp__olivia__ping` invoked live in Claude Code `2.1.330` via `.mcp.json`)

---

## 1. Explicit Tool & Protocol Coverage Matrix

| Surface / Tool | Catalog (`tools/list` / unit tests) | Subprocess Stdio Harness (`test_subprocess_mcp_serve_roundtrip`) | Live Claude Code `2.1.330` (`.mcp.json`) | Notes |
|---|---|---|---|---|
| `.mcp.json` registration (`olivia mcp-serve`) | Verified (`test_mcp_json_registration_and_required_tools_catalog`) | Spawned `python -m olivia mcp-serve` | Launched `.venv\Scripts\olivia.exe mcp-serve` via `--strict-mcp-config --mcp-config .mcp.json` | Live discovery confirmed |
| JSON-RPC `initialize` / `notifications/initialized` / `tools/list` | Verified | **Invoked** | **Invoked** (by Claude Code MCP client) | Protocol handshake |
| JSON-RPC `ping` (`method: "ping"` → `{}`) | Verified (`test_ping_and_notifications`) | **Invoked** (`id=2` → `{}`) | Protocol utility method | MCP `2024-11-05` protocol ping |
| `ping` *(callable MCP tool added in Round 4)* | **Discovered in `tools/list`** + unit-tested | **Invoked** (`id=8` → `{"ok": true, "server": "olivia", "version": "0.4.0"}`) | **Invoked live** (`session_id=4b18d11b-96bc-45dc-89d5-60df6cdfb71d`, `mcp__olivia__ping` → `{"ok": true, "server": "olivia", "version": "0.4.0"}`) | Satisfies `#15` callable `ping` requirement directly |
| `molar_mass` | Discovered + unit-tested | **Invoked** | **Invoked live** (`session_id=721cc990`, `H2SO4` → `98.072 g/mol`) | Full end-to-end |
| `convert_units` | Discovered + unit-tested | **Invoked** | **Invoked live** (`session_id=721cc990`, `100 km/h` → `27.7778 m/s`) | Full end-to-end |
| `notebook_add` | Discovered + unit-tested | **Invoked** | **Invoked live** (`session_id=721cc990`, saved `note_ecbd7d48`) | Full end-to-end |
| `notebook_entries` *(added in this PR)* | Discovered + unit-tested | **Invoked** | **Invoked live** (`session_id=721cc990`, read back `note_ecbd7d48`) | Full end-to-end |
| `olivia_ask`, `olivia_solve`, `olivia_research`, `olivia_worksheet`, `balance_equation`, `physical_constant`, `notebook_search`, `meta_stats`, `olivia_study_plan`, `olivia_flashcards`, `olivia_quiz`, `olivia_lab`, `literature_search`, `python_exec` (14 tools) | **Discovered in `tools/list` + unit-tested** (`tests/test_mcp/test_server.py`) | Discovered via `tools/list` (not individually invoked in subprocess test) | Discovered by Claude Code MCP client (not individually invoked in the 5-tool live sessions) | Catalog & handlers verified; live per-tool invocation not claimed |

---

## 2. Live Claude Code Round-Trip Observed Sessions

1. **Session 1 (`2026-11-23`, `session_id=721cc990-87f2-4e76-b400-bd70d79d9232`, `Claude Code 2.1.330` / `claude-sonnet-5-5`, `num_turns=6`, `is_error=false`, `permission_denials=[]`):**
   - `mcp__olivia__molar_mass("H2SO4")` → `98.072 g/mol`
   - `mcp__olivia__convert_units(100, "km/h", "m/s")` → `27.77777777777778 m/s`
   - `mcp__olivia__notebook_add(kind="note", ...)` → saved `note_ecbd7d48` (corroborated on disk in `~/.olivia/notebook.json`, then cleaned up)
   - `mcp__olivia__notebook_entries(kind="note")` → returned `note_ecbd7d48`
2. **Session 2 (`2026-11-23`, `session_id=4b18d11b-96bc-45dc-89d5-60df6cdfb71d`, `Claude Code 2.1.330` / `claude-sonnet-5-5`, `num_turns=3`, `is_error=false`, `permission_denials=[]`):**
   - `mcp__olivia__ping()` → `{"ok": true, "server": "olivia", "version": "0.4.0"}`

---

## 3. Automated Checks Executed

- `uv run --python 3.12 --extra dev --extra science ruff check src tests` — `All checks passed!`
- `uv run --python 3.12 --extra dev --extra science ruff format --check src tests` — `90 files already formatted`
- `uv run --python 3.12 --extra dev --extra science mypy src/olivia` — `Success: no issues found in 65 source files`
- `uv run --python 3.12 --extra dev --extra science pytest tests/ -q` — `379 passed, 2 skipped` (incl. 22 tests in `tests/test_mcp/test_server.py`)
- `uv run --python 3.12 --extra dev --extra science olivia eval --check` — `All gates hold.`
