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


def test_registry_list_and_names_are_consistent():
    registry = ToolRegistry()
    registry.register(Tool(name="beta", description="", fn=lambda: "b"))
    registry.register(Tool(name="alpha", description="", fn=lambda: "a"))
    assert registry.names() == ["alpha", "beta"]
    assert {tool.name for tool in registry.list()} == {"alpha", "beta"}


def test_validate_arguments_handles_union_and_unsupported_types():
    schema = {
        "properties": {
            "untyped": {},
            "nullable_str": {"type": ["string", "null"]},
        }
    }
    # Positive cases: untyped accepts values; union accepts declared members only.
    assert validate_arguments(schema, {"untyped": 42, "nullable_str": "ok"}) is None
    assert validate_arguments(schema, {"nullable_str": None}) is None
    # Negative cases: union rejects undeclared types (e.g. int, bool).
    assert (
        validate_arguments(schema, {"nullable_str": 42})
        == "argument 'nullable_str' must be one of types ['string', 'null']"
    )
    assert (
        validate_arguments(schema, {"nullable_str": True})
        == "argument 'nullable_str' must be one of types ['string', 'null']"
    )
    # Unsupported or malformed union / non-string type declarations fail closed.
    assert "unsupported schema type" in (
        validate_arguments({"properties": {"x": {"type": []}}}, {"x": "a"}) or ""
    )
    assert "unsupported schema type" in (
        validate_arguments({"properties": {"x": {"type": ["string", "custom"]}}}, {"x": "a"}) or ""
    )
    assert "unsupported schema type" in (
        validate_arguments({"properties": {"x": {"type": 123}}}, {"x": "a"}) or ""
    )
