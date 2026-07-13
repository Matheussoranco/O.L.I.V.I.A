"""LLM layer: tiered clients + Hermes tool-calling protocol."""

from olivia.llm.client import (
    AnthropicClient,
    LLMClient,
    LLMResponse,
    NullClient,
    OllamaClient,
    get_client,
)
from olivia.llm.hermes import (
    AgentResult,
    HermesAgent,
    ToolCall,
    format_tool_response,
    parse_tool_calls,
    render_tool_prompt,
    strip_think,
)

__all__ = [
    "AgentResult",
    "AnthropicClient",
    "HermesAgent",
    "LLMClient",
    "LLMResponse",
    "NullClient",
    "OllamaClient",
    "ToolCall",
    "format_tool_response",
    "get_client",
    "parse_tool_calls",
    "render_tool_prompt",
    "strip_think",
]
