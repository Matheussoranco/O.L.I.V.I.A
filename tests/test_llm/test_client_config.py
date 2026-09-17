"""LLM factory: per-config cache, documented refresh, honest availability."""

from __future__ import annotations

import importlib.util

import pytest

from olivia.config import settings
from olivia.llm.client import (
    AnthropicClient,
    NullClient,
    OllamaClient,
    get_client,
    refresh_clients,
)

_HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None


def test_get_client_cache_clear_alias_still_works():
    get_client.cache_clear()  # conftest contract: must not raise


def test_factory_keys_by_provider_and_base_url(monkeypatch):
    monkeypatch.setattr(settings.llm, "provider", "ollama")
    monkeypatch.setattr(settings.llm, "ollama_base_url", "http://localhost:11434")
    first = get_client()
    assert isinstance(first, OllamaClient)

    monkeypatch.setattr(settings.llm, "ollama_base_url", "http://example.invalid:11434")
    second = get_client()
    assert isinstance(second, OllamaClient)
    assert second is not first  # a tier-only cache would return the stale client here
    assert second.base_url == "http://example.invalid:11434"


def test_refresh_clients_rebuilds(monkeypatch):
    monkeypatch.setattr(settings.llm, "provider", "none")
    assert isinstance(get_client(), NullClient)
    refresh_clients()
    assert isinstance(get_client(), NullClient)


def test_anthropic_available_requires_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert AnthropicClient().available is False


@pytest.mark.skipif(not _HAS_ANTHROPIC, reason="anthropic SDK not installed")
def test_anthropic_available_with_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-key")
    assert AnthropicClient().available is True


def test_ollama_probe_has_ttl_not_permanent_memo(monkeypatch):
    import httpx

    calls = []

    def _offline(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("offline")

    monkeypatch.setattr(httpx, "get", _offline)
    client = OllamaClient(base_url="http://localhost:11434")
    assert client.available is False
    assert client.available is False
    assert len(calls) == 1  # second read served from the TTL window

    client._reachable_at -= 61.0  # expire the TTL window
    assert client.available is False
    assert len(calls) == 2  # re-probed instead of memoised forever
