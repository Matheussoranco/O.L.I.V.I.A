"""O.L.I.V.I.A. — Open Learning Intelligence & Virtual Investigation Assistant.

An AI agent specialised in study, learning, and scientific research and
discovery.  Architectural lineage:

* **I.S.A.A.C.** — LangGraph cognitive cycle, Mixture-of-Experts routing,
  meta-learning from task outcomes, MCP co-working with Claude.
* **Nous Research Hermes** — model-agnostic tool calling over a plain-text
  ``<tool_call>`` protocol, so any LLM (local Ollama models included) can
  drive the agent loop; reasoning traces via ``<think>`` blocks.
* **Claude for Science** — the scientific workflow as a first-class loop:
  literature review → hypothesis → experiment design → analysis →
  Popperian critique → scientific writing.
"""

from __future__ import annotations

__version__ = "0.2.1"
__all__ = ["__version__"]
