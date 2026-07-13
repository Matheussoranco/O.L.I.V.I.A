"""Central configuration — pydantic-settings, ``OLIVIA_`` environment prefix.

Nested keys use ``__`` as the delimiter, e.g. ``OLIVIA_LLM__PROVIDER=ollama``.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseModel):
    """Which model backend to use, per tier.

    ``provider``:
        * ``auto``      — Anthropic if credentials are visible, else none.
        * ``anthropic`` — force the Anthropic SDK (works with ``ant auth login``
          profiles even when ``ANTHROPIC_API_KEY`` is unset).
        * ``ollama``    — local OpenAI-compatible/Ollama server over httpx.
        * ``none``      — deterministic offline mode (NullClient).
    """

    provider: str = "auto"
    model: str = "claude-opus-4-8"
    """Default tier — the workhorse model."""
    fast_model: str = "claude-haiku-4-5"
    """Cheap/fast tier for routing, extraction, and short structured calls."""
    strong_model: str = "claude-opus-4-8"
    """Strong tier for synthesis, critique, and scientific writing."""
    max_tokens: int = 4096
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    temperature: float | None = None
    """Only forwarded to the Ollama backend; Anthropic 4.7+/Fable reject it."""


class ResearchSettings(BaseModel):
    max_papers: int = 12
    max_hypotheses: int = 3
    max_revisions: int = 2
    """How many critique→revise loops the research cycle may run."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OLIVIA_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    research: ResearchSettings = Field(default_factory=ResearchSettings)
    home_dir: Path = Field(default_factory=lambda: Path.home() / ".olivia")
    anthropic_api_key: str = ""
    """Optional explicit key; falls back to ANTHROPIC_API_KEY / ant profiles."""

    def data_dir(self) -> Path:
        """Return ``~/.olivia`` (or the override), creating it if needed."""
        self.home_dir.mkdir(parents=True, exist_ok=True)
        return self.home_dir

    def resolved_anthropic_key(self) -> str:
        return self.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")


settings = Settings()
