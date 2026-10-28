"""Tool registry — schema validation and guarded execution."""

from __future__ import annotations

from olivia.tools.registry import Tool, ToolRegistry, validate_arguments


def test_non_object_arguments_are_rejected():
    assert validate_arguments({"properties": {}}, ["not", "an", "object"]) == (
        "arguments must be a JSON object"
    )


def test_execute_rejects_non_object_arguments():
    registry = ToolRegistry()
    registry.register(Tool(name="echo", description="", fn=lambda: "ok"))
    assert registry.execute("echo", ["bad"]).startswith("error: arguments must be a JSON object")
    assert registry.execute("echo", []).startswith("error: arguments must be a JSON object")


def test_non_finite_numbers_are_rejected():
    schema = {"properties": {"x": {"type": "number"}}}
    assert validate_arguments(schema, {"x": float("nan")}) == "argument 'x' must be finite"
    assert validate_arguments(schema, {"x": float("inf")}) == "argument 'x' must be finite"
    assert validate_arguments(schema, {"x": 1.5}) is None
