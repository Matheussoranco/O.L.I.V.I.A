"""MCP stdio server — Claude co-works with O.L.I.V.I.A. over JSON-RPC 2.0.

Zero-dependency implementation of the Model Context Protocol's stdio
transport (same approach as I.S.A.A.C.): newline-delimited JSON-RPC on
stdin/stdout, logging strictly to stderr.  Register in Claude Code with::

    {"mcpServers": {"olivia": {"command": "olivia", "args": ["mcp-serve"]}}}
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from olivia import __version__

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
_MAX_RESPONSE_CHARS = 50_000
# Derived, never hardcoded: a literal here silently drifts from the package
# version on every release and reports a stale version to the MCP client.
SERVER_INFO = {"name": "olivia", "version": __version__}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _olivia_ask(question: str, mode: str = "cascade") -> Any:
    from olivia.experts import answer

    result = answer(question, mode=mode)
    return {"answer": result.answer, "expert": result.expert, "confidence": result.confidence}


def _olivia_research(question: str) -> Any:
    from olivia.core.graph import run_cycle

    state = run_cycle(question, mode="research")
    report = state.get("report")
    return report.report_markdown if report else "research cycle produced no report"


def _olivia_solve(problem: str, subject: str = "auto") -> Any:
    from olivia.study import solve_problem

    solution = solve_problem(problem, subject=subject)
    return {
        "answer": solution.final_answer,
        "method": solution.method,
        "confidence": solution.confidence,
        "steps": [
            {"n": s.n, "description": s.description, "result": s.result} for s in solution.steps
        ],
    }


def _olivia_worksheet(topic: str, n: int = 5, difficulty: str = "medium") -> Any:
    from olivia.study import generate_worksheet, worksheet_to_markdown

    solutions = generate_worksheet(topic, n=n, difficulty=difficulty, seed=0)
    if not solutions:
        return "no worksheet generated (LLM backend or a maths topic required)"
    return worksheet_to_markdown(solutions, topic=topic)


def _molar_mass(formula: str) -> Any:
    from olivia.tools.chemistry import molar_mass

    return molar_mass(formula)


def _balance_equation(equation: str) -> Any:
    from olivia.tools.chemistry import balance_equation

    return balance_equation(equation)


def _convert_units(value: float, from_unit: str, to_unit: str) -> Any:
    from olivia.tools.units import convert_units

    return convert_units(value, from_unit, to_unit)


def _physical_constant(query: str) -> Any:
    from olivia.tools.physics import physical_constant

    return physical_constant(query)


def _olivia_study_plan(topic: str, goal: str = "", weeks: int = 4) -> Any:
    from olivia.study import make_study_plan, plan_to_markdown

    return plan_to_markdown(make_study_plan(topic, goal=goal, weeks=weeks))


def _olivia_flashcards(topic: str, content: str = "", n: int = 10) -> Any:
    from olivia.study import Deck, generate_flashcards

    cards = generate_flashcards(topic, content=content, n=n)
    if cards:
        Deck(topic).add(cards)
    return [{"front": c.front, "back": c.back} for c in cards]


def _olivia_quiz(topic: str, content: str = "", n: int = 5) -> Any:
    from olivia.study import generate_quiz

    return [asdict(q) for q in generate_quiz(topic, content=content, n=n)]


def _literature_search(query: str, max_results: int = 10, allow_network: bool = False) -> Any:
    from olivia.tools.literature import literature_search

    return [asdict(p) for p in literature_search(query, max_results, allow_network=allow_network)]


def _python_exec(code: str, timeout: float = 30.0) -> Any:
    from olivia.tools.science import python_exec

    return python_exec(code, timeout)


def _notebook_add(kind: str, content: str, tags: list[str] | None = None) -> Any:
    from olivia.memory import Notebook

    return Notebook().add(kind, content, tags=tags)


def _notebook_search(query: str = "", kind: str | None = None, limit: int = 10) -> Any:
    from olivia.memory import Notebook

    return Notebook().search(query, kind=kind, limit=limit)


def _meta_stats() -> Any:
    from olivia.meta import get_meta_learner

    return get_meta_learner().stats()


def _lab_investigate(question: str, rounds: int = 1) -> Any:
    from olivia.agents import ResearchLab

    return ResearchLab().investigate(question, rounds=rounds)


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


TOOLS: dict[str, tuple[str, dict[str, Any], Callable[..., Any]]] = {
    "olivia_ask": (
        "Ask O.L.I.V.I.A. a question via its Mixture-of-Experts (math, stats, code, "
        "literature, general).",
        _schema(
            {
                "question": {"type": "string"},
                "mode": {"type": "string", "enum": ["cascade", "single"]},
            },
            ["question"],
        ),
        _olivia_ask,
    ),
    "olivia_research": (
        "Run a full scientific discovery cycle: literature → hypotheses → experiments → "
        "analysis → critique → report. Returns the report markdown.",
        _schema({"question": {"type": "string"}}, ["question"]),
        _olivia_research,
    ),
    "olivia_solve": (
        "Solve a STEM problem step by step (GPAI-style). Symbolic-first: sympy for "
        "maths, periodic table for chemistry, CODATA for physics, dimensional "
        "analysis for units. Returns ordered steps and a final answer.",
        _schema(
            {
                "problem": {"type": "string"},
                "subject": {
                    "type": "string",
                    "enum": ["auto", "math", "chemistry", "physics", "units"],
                },
            },
            ["problem"],
        ),
        _olivia_solve,
    ),
    "olivia_worksheet": (
        "Generate a practice worksheet with a worked-solution answer key. Offline it "
        "produces randomised maths problems (linear, quadratic, derivative, arithmetic).",
        _schema(
            {
                "topic": {"type": "string"},
                "n": {"type": "integer", "minimum": 1, "maximum": 100},
                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
            },
            ["topic"],
        ),
        _olivia_worksheet,
    ),
    "molar_mass": (
        "Compute the molar mass (g/mol) of a chemical formula, with a per-element "
        "breakdown. Understands groups and hydrates (e.g. CuSO4·5H2O).",
        _schema({"formula": {"type": "string"}}, ["formula"]),
        _molar_mass,
    ),
    "balance_equation": (
        "Balance a chemical equation (e.g. 'H2 + O2 -> H2O') by exact conservation of atoms.",
        _schema({"equation": {"type": "string"}}, ["equation"]),
        _balance_equation,
    ),
    "convert_units": (
        "Convert a physical quantity between units (SI, imperial, temperature).",
        _schema(
            {
                "value": {"type": "number"},
                "from_unit": {"type": "string"},
                "to_unit": {"type": "string"},
            },
            ["value", "from_unit", "to_unit"],
        ),
        _convert_units,
    ),
    "physical_constant": (
        "Look up a physical constant by name or symbol (e.g. 'speed of light', "
        "'Planck constant', 'N_A'). Returns value and SI unit.",
        _schema({"query": {"type": "string"}}, ["query"]),
        _physical_constant,
    ),
    "olivia_study_plan": (
        "Create a week-by-week study plan for a topic.",
        _schema(
            {
                "topic": {"type": "string"},
                "goal": {"type": "string"},
                "weeks": {"type": "integer", "minimum": 1, "maximum": 52},
            },
            ["topic"],
        ),
        _olivia_study_plan,
    ),
    "olivia_flashcards": (
        "Generate spaced-repetition flashcards for a topic (saved to the topic's SM-2 deck).",
        _schema(
            {
                "topic": {"type": "string"},
                "content": {"type": "string"},
                "n": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            ["topic"],
        ),
        _olivia_flashcards,
    ),
    "olivia_quiz": (
        "Generate a quiz on a topic.",
        _schema(
            {
                "topic": {"type": "string"},
                "content": {"type": "string"},
                "n": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            ["topic"],
        ),
        _olivia_quiz,
    ),
    "olivia_lab": (
        "Multi-agent seminar on a question: researcher drafts, critic attacks, writer "
        "synthesises. Requires an LLM backend.",
        _schema(
            {
                "question": {"type": "string"},
                "rounds": {"type": "integer", "minimum": 1, "maximum": 5},
            },
            ["question"],
        ),
        _lab_investigate,
    ),
    "literature_search": (
        "Search arXiv, Crossref, and Semantic Scholar; returns deduplicated records.",
        _schema(
            {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
                "allow_network": {"type": "boolean", "default": False},
            },
            ["query"],
        ),
        _literature_search,
    ),
    "python_exec": (
        "Execute Python code in an isolated subprocess; returns {ok, stdout, stderr}.",
        _schema(
            {
                "code": {"type": "string"},
                "timeout": {"type": "number", "minimum": 0.1, "maximum": 30.0},
            },
            ["code"],
        ),
        _python_exec,
    ),
    "notebook_add": (
        "Append an entry to O.L.I.V.I.A.'s lab notebook.",
        _schema(
            {
                "kind": {"type": "string"},
                "content": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            ["kind", "content"],
        ),
        _notebook_add,
    ),
    "notebook_search": (
        "Keyword-search the lab notebook.",
        _schema(
            {
                "query": {"type": "string"},
                "kind": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            [],
        ),
        _notebook_search,
    ),
    "meta_stats": (
        "O.L.I.V.I.A.'s meta-learning statistics: strategy win-rates per task kind.",
        _schema({}, []),
        _meta_stats,
    ),
}


# ---------------------------------------------------------------------------
# JSON-RPC plumbing
# ---------------------------------------------------------------------------


def _handle(request: dict[str, Any]) -> dict[str, Any] | None:
    """Dispatch one JSON-RPC request; None for notifications."""
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        request_id = request.get("id") if isinstance(request, dict) else None
        return _error(request_id, -32600, "invalid request")
    method = request.get("method", "")
    request_id = request.get("id")
    params = request.get("params", {})
    if not isinstance(params, dict):
        return _error(request_id, -32602, "params must be an object")

    if method == "initialize":
        result: Any = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {"name": name, "description": description, "inputSchema": schema}
                for name, (description, schema, _) in TOOLS.items()
            ]
        }
    elif method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        entry = TOOLS.get(name)
        if entry is None:
            return _error(request_id, -32602, f"unknown tool '{name}'")
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return _error(request_id, -32602, "tool name and arguments are invalid")
        validation_error = _validate_arguments(entry[1], arguments)
        if validation_error:
            return _error(request_id, -32602, validation_error)
        try:
            output = entry[2](**arguments)
            text = (
                output
                if isinstance(output, str)
                else json.dumps(output, ensure_ascii=False, default=str, indent=2)
            )
            if len(text) > _MAX_RESPONSE_CHARS:
                text = text[:_MAX_RESPONSE_CHARS] + "\n[response truncated]"
            result = {"content": [{"type": "text", "text": text}], "isError": False}
        except Exception as exc:
            logger.exception("tool %s failed", name)
            result = {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True}
    elif method in ("notifications/initialized", "notifications/cancelled"):
        return None
    elif method == "ping":
        result = {}
    else:
        if request_id is None:
            return None
        return _error(request_id, -32601, f"method not found: {method}")

    if request_id is None:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    """Validate the small JSON-schema subset used by the local tool registry."""
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    missing = [name for name in required if name not in arguments]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}"
    unknown = [name for name in arguments if name not in properties]
    if unknown:
        return f"unknown argument(s): {', '.join(unknown)}"

    def check(name: str, value: Any, rule: dict[str, Any]) -> str | None:
        kind = rule.get("type")
        valid = {
            "string": isinstance(value, str),
            "boolean": isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "array": isinstance(value, list),
            "object": isinstance(value, dict),
        }.get(kind, True)
        if not valid:
            return f"argument '{name}' must be {kind}"
        if "enum" in rule and value not in rule["enum"]:
            return f"argument '{name}' must be one of {rule['enum']}"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in rule and value < rule["minimum"]:
                return f"argument '{name}' is below the minimum"
            if "maximum" in rule and value > rule["maximum"]:
                return f"argument '{name}' exceeds the maximum"
        if isinstance(value, list) and isinstance(rule.get("items"), dict):
            for index, item in enumerate(value):
                error = check(f"{name}[{index}]", item, rule["items"])
                if error:
                    return error
        return None

    for name, value in arguments.items():
        error = check(name, value, properties[name])
        if error:
            return error
    return None


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve() -> None:
    """Blocking stdio loop: one JSON-RPC message per line."""
    # A subprocess's stdio streams default to the platform's legacy codepage
    # on Windows (cp1252 etc.), not UTF-8. Tool descriptions, research
    # reports, and literature abstracts are arbitrary Unicode text (e.g. the
    # 'olivia_research' description below contains '→'), so the very first
    # non-ASCII character written would otherwise crash the server with
    # UnicodeEncodeError before any client ever sees a response.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    logger.warning("olivia MCP server listening on stdio")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            sys.stdout.flush()
            continue
        response = _handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, default=str) + "\n")
            sys.stdout.flush()
