"""MCP stdio server — JSON-RPC 2.0 dispatch and tool execution, offline."""

from __future__ import annotations

import io
import json
import sys

from olivia.mcp.server import PROTOCOL_VERSION, TOOLS, _handle, serve


def _call(name: str, arguments: dict | None = None, request_id: int = 1) -> dict:
    return _handle(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
    )


def _text(response: dict) -> str:
    return response["result"]["content"][0]["text"]


# ---------------------------------------------------------------------------
# Protocol plumbing
# ---------------------------------------------------------------------------


def test_initialize_handshake():
    response = _handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert response["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert response["result"]["serverInfo"]["name"] == "olivia"


def test_tools_list_matches_registry():
    response = _handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = response["result"]["tools"]
    assert {t["name"] for t in tools} == set(TOOLS)
    assert all(t["description"] and t["inputSchema"]["type"] == "object" for t in tools)


def test_ping_and_notifications():
    assert _handle({"jsonrpc": "2.0", "id": 3, "method": "ping"})["result"] == {}
    assert _handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_and_unknown_tool():
    response = _handle({"jsonrpc": "2.0", "id": 4, "method": "no/such"})
    assert response["error"]["code"] == -32601
    # Unknown notification (no id) stays silent per JSON-RPC.
    assert _handle({"jsonrpc": "2.0", "method": "no/such"}) is None

    response = _call("no_such_tool")
    assert response["error"]["code"] == -32602


def test_tool_exception_returns_is_error_result():
    response = _call("notebook_add", {"kind": "note"})  # missing required 'content'
    assert response["result"]["isError"] is True
    assert "error" in _text(response)


# ---------------------------------------------------------------------------
# Tools end-to-end (offline)
# ---------------------------------------------------------------------------


def test_python_exec_tool():
    response = _call("python_exec", {"code": "print(2 + 3)"})
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


def test_notebook_add_then_search():
    added = _call(
        "notebook_add", {"kind": "note", "content": "gravitational lensing", "tags": ["gr"]}
    )
    assert json.loads(_text(added))["kind"] == "note"

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
