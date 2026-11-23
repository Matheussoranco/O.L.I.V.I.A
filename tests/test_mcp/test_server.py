"""MCP stdio server — JSON-RPC 2.0 dispatch and tool execution, offline."""

from __future__ import annotations

import io
import json
import sys

from olivia.mcp.server import PROTOCOL_VERSION, TOOLS, _handle, serve


def _call(name: str, arguments: dict | None = None, request_id: int = 1) -> dict:
    res = _handle(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
    )
    assert res is not None
    return res


def _text(response: dict) -> str:
    return response["result"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# Protocol plumbing
# ---------------------------------------------------------------------------


def test_initialize_handshake():
    response = _handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert response is not None
    assert response["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert response["result"]["serverInfo"]["name"] == "olivia"


def test_tools_list_matches_registry():
    response = _handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert response is not None
    tools = response["result"]["tools"]
    assert {t["name"] for t in tools} == set(TOOLS)
    assert all(t["description"] and t["inputSchema"]["type"] == "object" for t in tools)


def test_ping_and_notifications():
    res = _handle({"jsonrpc": "2.0", "id": 3, "method": "ping"})
    assert res is not None and res["result"] == {}
    tool_res = json.loads(_text(_call("ping")))
    assert tool_res["ok"] is True and tool_res["server"] == "olivia"
    assert _handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_and_unknown_tool():
    response = _handle({"jsonrpc": "2.0", "id": 4, "method": "no/such"})
    assert response is not None
    assert response["error"]["code"] == -32601
    # Unknown notification (no id) stays silent per JSON-RPC.
    assert _handle({"jsonrpc": "2.0", "method": "no/such"}) is None

    response = _call("no_such_tool")
    assert response["error"]["code"] == -32602


def test_non_string_tool_name_is_an_invalid_params_error():
    response = _handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": ["olivia_ask"], "arguments": {}},
        }
    )
    assert response is not None
    assert response["error"]["code"] == -32602


def test_tool_exception_returns_is_error_result():
    response = _call("notebook_add", {"kind": "note"})  # missing required 'content'
    assert response["error"]["code"] == -32602
    assert "content" in response["error"]["message"]


# ---------------------------------------------------------------------------
# Tools end-to-end (offline)
# ---------------------------------------------------------------------------


def test_python_exec_tool():
    # Sem confirmação explícita o gate risk=5 bloqueia sem executar.
    blocked = _call("python_exec", {"code": "print(2 + 3)"})
    payload_blocked = json.loads(_text(blocked))
    assert payload_blocked["ok"] is False
    assert "allow_risky" in payload_blocked["stderr"]

    response = _call("python_exec", {"code": "print(2 + 3)", "allow_risky": True})
    payload = json.loads(_text(response))
    assert payload["ok"] and payload["stdout"].strip() == "5"
    assert response["result"]["isError"] is False


def test_olivia_ask_tool_routes_to_stats():
    response = _call(
        "olivia_ask",
        {"question": "What sample size do I need to detect an effect size of 0.5?"},
    )
    payload = json.loads(_text(response))
    assert payload["expert"] == "stats"
    assert "63" in payload["answer"]


def test_olivia_study_plan_tool():
    response = _call("olivia_study_plan", {"topic": "calculus", "weeks": 2})
    assert "# Study plan: calculus" in _text(response)


def test_notebook_add_entries_and_search():
    added = _call(
        "notebook_add", {"kind": "note", "content": "gravitational lensing", "tags": ["gr"]}
    )
    assert json.loads(_text(added))["kind"] == "note"

    listed = json.loads(_text(_call("notebook_entries", {"kind": "note", "limit": 10})))
    assert len(listed) == 1
    assert listed[0]["content"] == "gravitational lensing"

    found = json.loads(_text(_call("notebook_search", {"query": "lensing"})))
    assert len(found) == 1
    assert found[0]["content"] == "gravitational lensing"


def test_meta_stats_tool():
    payload = json.loads(_text(_call("meta_stats")))
    assert set(payload) == {"total", "by_task"}


def test_olivia_lab_offline_reports_llm_unavailable():
    payload = json.loads(_text(_call("olivia_lab", {"question": "why sleep?"})))
    assert payload["error"] == "llm unavailable"


def test_literature_search_offline_returns_empty_list():
    assert json.loads(_text(_call("literature_search", {"query": "anything"}))) == []


def test_olivia_solve_tool_routes_to_chemistry():
    payload = json.loads(_text(_call("olivia_solve", {"problem": "molar mass of H2O"})))
    assert payload["method"] == "chemistry"
    assert "18" in payload["answer"]
    assert payload["steps"]


def test_molar_mass_tool():
    payload = json.loads(_text(_call("molar_mass", {"formula": "H2SO4"})))
    assert payload["ok"] and round(payload["molar_mass"]) == 98


def test_balance_equation_tool():
    payload = json.loads(_text(_call("balance_equation", {"equation": "H2 + O2 -> H2O"})))
    assert payload["ok"] and payload["balanced"] == "2 H2 + O2 -> 2 H2O"


def test_convert_units_tool():
    payload = json.loads(
        _text(_call("convert_units", {"value": 1, "from_unit": "km", "to_unit": "m"}))
    )
    assert payload["ok"] and payload["value"] == 1000.0


def test_physical_constant_tool():
    payload = json.loads(_text(_call("physical_constant", {"query": "speed of light"})))
    assert payload["ok"] and payload["value"] == 299792458.0


def test_olivia_worksheet_tool_offline_maths():
    text = _text(_call("olivia_worksheet", {"topic": "linear equations", "n": 3}))
    assert "# Worksheet: linear equations" in text
    assert "## Answer key" in text


# ---------------------------------------------------------------------------
# serve() — the stdio loop itself
# ---------------------------------------------------------------------------


def test_serve_stdio_roundtrip(monkeypatch, capsys):
    lines = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            "this is not json",
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            "",
        ]
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(lines))
    serve()

    out_lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    assert len(out_lines) == 3
    assert out_lines[0]["id"] == 1 and "result" in out_lines[0]
    assert out_lines[1]["error"]["code"] == -32700  # parse error
    assert out_lines[2]["id"] == 2 and "tools" in out_lines[2]["result"]


def test_mcp_json_registration_and_required_tools_catalog():
    from pathlib import Path

    mcp_json = Path(__file__).resolve().parents[2] / ".mcp.json"
    cfg = json.loads(mcp_json.read_text(encoding="utf-8"))
    olivia_srv = cfg["mcpServers"]["olivia"]
    assert olivia_srv["command"] == "olivia"
    assert olivia_srv["args"] == ["mcp-serve"]

    # Every tool listed in T7 (#15) must be registered and discoverable via tools/list.
    required = {
        "olivia_ask",
        "olivia_solve",
        "olivia_research",
        "olivia_worksheet",
        "molar_mass",
        "balance_equation",
        "convert_units",
        "physical_constant",
        "olivia_study_plan",
        "olivia_flashcards",
        "olivia_quiz",
        "olivia_lab",
        "literature_search",
        "python_exec",
        "notebook_add",
        "notebook_search",
        "notebook_entries",
        "meta_stats",
        "ping",
    }
    assert required.issubset(set(TOOLS))


def test_subprocess_mcp_serve_roundtrip(tmp_path):
    """End-to-end stdio JSON-RPC round-trip spawning `python -m olivia mcp-serve`."""
    import os
    import subprocess

    env = dict(os.environ)
    env["OLIVIA_HOME_DIR"] = str(tmp_path)
    env["OLIVIA_LLM__PROVIDER"] = "none"

    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "molar_mass", "arguments": {"formula": "H2O"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "convert_units",
                "arguments": {"value": 100, "from_unit": "celsius", "to_unit": "fahrenheit"},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "notebook_add",
                "arguments": {"kind": "finding", "content": "MCP stdio roundtrip ok"},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "notebook_entries", "arguments": {"kind": "finding"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "ping", "arguments": {}},
        },
    ]
    stdin_payload = "\n".join(json.dumps(req) for req in requests) + "\n"
    proc = subprocess.run(
        [sys.executable, "-m", "olivia", "mcp-serve"],
        input=stdin_payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
        check=True,
    )
    responses = {
        obj["id"]: obj for obj in (json.loads(line) for line in proc.stdout.splitlines() if line)
    }
    assert set(responses) == {1, 2, 3, 4, 5, 6, 7, 8}
    assert responses[1]["result"]["serverInfo"]["name"] == "olivia"
    assert responses[2]["result"] == {}
    tool_names = {t["name"] for t in responses[3]["result"]["tools"]}
    assert {"notebook_entries", "ping"}.issubset(tool_names) and len(tool_names) >= 19

    h2o = json.loads(responses[4]["result"]["content"][0]["text"])
    assert h2o["ok"] and round(h2o["molar_mass"], 2) == 18.02
    temp = json.loads(responses[5]["result"]["content"][0]["text"])
    assert temp["ok"] and temp["value"] == 212.0
    entries = json.loads(responses[7]["result"]["content"][0]["text"])
    assert len(entries) == 1 and entries[0]["content"] == "MCP stdio roundtrip ok"
    ping_tool = json.loads(responses[8]["result"]["content"][0]["text"])
    assert ping_tool["ok"] is True and ping_tool["server"] == "olivia"
