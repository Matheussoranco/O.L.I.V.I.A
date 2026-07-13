"""Tooling package: registry + concrete research tools."""

from olivia.tools.registry import Tool, ToolRegistry, default_registry


def build_default_registry() -> ToolRegistry:
    """Return :data:`default_registry` with every built-in tool registered."""
    from olivia.tools import literature, science

    if default_registry.get("literature_search") is None:
        literature.register_tools(default_registry)
        science.register_tools(default_registry)
    return default_registry


__all__ = ["Tool", "ToolRegistry", "build_default_registry", "default_registry"]
