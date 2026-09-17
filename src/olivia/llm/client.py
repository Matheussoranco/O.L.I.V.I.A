"""LLM client abstraction — Anthropic, Ollama, or deterministic offline Null.

Design rule (Hermes-inspired): every consumer takes ``client: LLMClient | None``
and must degrade gracefully when ``client.available`` is ``False``, so the whole
system imports, runs, and tests **offline** with no keys and no network.

Tiers mirror I.S.A.A.C.: ``get_client()`` default, ``get_client("fast")`` for
routing/extraction, ``get_client("strong")`` for synthesis and critique.
"""

from __future__ import annotations

import abc
import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal

logger = logging.getLogger(__name__)

Tier = Literal["default", "fast", "strong"]


@dataclass
class LLMResponse:
    """A single completion."""

    text: str = ""
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None
    error: str = ""

    def ok(self) -> bool:
        return not self.error and bool(self.text.strip())


class LLMClient(abc.ABC):
    """Minimal chat-completion interface shared by every backend."""

    name: str = "base"

    @property
    @abc.abstractmethod
    def available(self) -> bool:
        """Cheap check — no network round-trip unless unavoidable."""

    @abc.abstractmethod
    def complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Run one completion over ``[{'role': ..., 'content': ...}, ...]``."""

    def ask(self, prompt: str, system: str = "", max_tokens: int | None = None) -> str:
        """Convenience one-shot: returns the text (empty string on failure)."""
        resp = self.complete([{"role": "user", "content": prompt}], system, max_tokens)
        return resp.text


# ---------------------------------------------------------------------------
# Null — deterministic offline backend
# ---------------------------------------------------------------------------


class NullClient(LLMClient):
    """No LLM configured; consumers must fall back to symbolic paths."""

    name = "null"

    @property
    def available(self) -> bool:
        return False

    def complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int | None = None,
    ) -> LLMResponse:
        return LLMResponse(text="", model="null", error="no LLM backend configured")


# ---------------------------------------------------------------------------
# Anthropic — official SDK (credentials via env key or `ant auth login`)
# ---------------------------------------------------------------------------


class AnthropicClient(LLMClient):
    name = "anthropic"

    def __init__(self, model: str | None = None, max_tokens: int | None = None) -> None:
        from olivia.config import settings

        self.model = model or settings.llm.model
        self.max_tokens = max_tokens or settings.llm.max_tokens
        self._client: Any = None

    def _sdk(self) -> Any:
        if self._client is None:
            import anthropic

            # Zero-arg constructor: resolves ANTHROPIC_API_KEY, auth tokens,
            # or an `ant auth login` profile — do not require an explicit key.
            from olivia.config import settings

            key = settings.resolved_anthropic_key()
            self._client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        return self._client

    @property
    def available(self) -> bool:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        from olivia.config import settings

        return bool(settings.resolved_anthropic_key())

    def complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int | None = None,
    ) -> LLMResponse:
        try:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens or self.max_tokens,
                "messages": messages,
            }
            if system:
                kwargs["system"] = system
            response = self._sdk().messages.create(**kwargs)
            if response.stop_reason == "refusal":
                return LLMResponse(model=self.model, raw=response, error="refusal")
            text = "".join(b.text for b in response.content if b.type == "text")
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
            return LLMResponse(text=text, model=self.model, usage=usage, raw=response)
        except Exception as exc:
            logger.warning("Anthropic completion failed: %s", exc)
            return LLMResponse(model=self.model, error=str(exc))


# ---------------------------------------------------------------------------
# Ollama — local models over the native /api/chat endpoint (httpx)
# ---------------------------------------------------------------------------


class OllamaClient(LLMClient):
    name = "ollama"

    #: How long a reachability probe stays valid before re-probing.
    probe_ttl_s: float = 60.0
    #: Short timeout so ``available`` stays a cheap check.
    probe_timeout_s: float = 1.0

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        from olivia.config import settings

        self.model = model or settings.llm.ollama_model
        self.base_url = (base_url or settings.llm.ollama_base_url).rstrip("/")
        self._reachable: bool | None = None
        self._reachable_at: float = 0.0
        self._probed_url: str | None = None

    @property
    def available(self) -> bool:
        now = time.monotonic()
        if (
            self._reachable is not None
            and self._probed_url == self.base_url
            and (now - self._reachable_at) < self.probe_ttl_s
        ):
            return self._reachable
        import httpx

        try:
            httpx.get(f"{self.base_url}/api/tags", timeout=self.probe_timeout_s)
            self._reachable = True
        except Exception:
            self._reachable = False
        self._reachable_at = now
        self._probed_url = self.base_url
        return self._reachable

    def complete(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        max_tokens: int | None = None,
    ) -> LLMResponse:
        import httpx

        from olivia.config import settings

        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        options: dict[str, Any] = {}
        if max_tokens:
            options["num_predict"] = max_tokens
        if settings.llm.temperature is not None:
            options["temperature"] = settings.llm.temperature
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": msgs, "stream": False, "options": options},
                timeout=300.0,
            )
            response.raise_for_status()
            data = response.json()
            return LLMResponse(
                text=data.get("message", {}).get("content", ""),
                model=self.model,
                raw=data,
            )
        except Exception as exc:
            logger.warning("Ollama completion failed: %s", exc)
            return LLMResponse(model=self.model, error=str(exc))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=32)
def _build_client(tier: Tier, provider: str, model: str, base_url: str) -> LLMClient:
    """Build (and cache) one client per ``(tier, provider, model, base_url)``."""
    if provider == "ollama":
        return OllamaClient(base_url=base_url)
    if provider == "anthropic":
        return AnthropicClient(model=model)
    return NullClient()


def get_client(tier: Tier = "default") -> LLMClient:
    """Return the configured client for a tier.

    Results are cached per ``(tier, provider, model, base_url)`` so a settings
    change yields a fresh client instead of a stale one. Call
    :func:`refresh_clients` (or ``get_client.cache_clear()``) after changing
    the configuration to drop cached instances eagerly.
    """
    from olivia.config import settings

    cfg = settings.llm
    model = {"default": cfg.model, "fast": cfg.fast_model, "strong": cfg.strong_model}[tier]
    provider = cfg.provider.lower()
    base_url = cfg.ollama_base_url

    if provider == "auto":
        # Anthropic only when credentials are explicitly visible, so a bare
        # offline checkout never fires network calls by surprise.
        provider = "anthropic" if settings.resolved_anthropic_key() else "none"
    if provider not in ("none", "ollama", "anthropic"):
        provider = "none"
    return _build_client(tier, provider, model, base_url)


def refresh_clients() -> None:
    """Drop all cached LLM clients; the next :func:`get_client` rebuilds them."""
    _build_client.cache_clear()


# Backwards compatibility: ``get_client.cache_clear()`` (lru_cache API) keeps
# working — it now clears the underlying per-config client cache.
get_client.cache_clear = refresh_clients  # type: ignore[attr-defined]
get_client.cache_info = _build_client.cache_info  # type: ignore[attr-defined]
