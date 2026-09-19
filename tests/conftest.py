"""Shared fixtures — every test runs offline against an isolated data dir."""

from __future__ import annotations

from typing import Any, cast

import pytest

from olivia.llm.client import LLMClient, LLMResponse

try:
    import langchain

    if not hasattr(langchain, "debug"):
        cast(Any, langchain).debug = False
except ImportError:
    pass


class FakeClient(LLMClient):
    """Deterministic LLM stand-in: replays canned responses, repeats the last."""

    name = "fake"

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses) or [""]
        self.calls: list[list[dict[str, str]]] = []

    @property
    def available(self) -> bool:
        return True

    def complete(
        self, messages: Any, system: str = "", max_tokens: int | None = None
    ) -> LLMResponse:
        self.calls.append(list(messages))
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        return LLMResponse(text=self._responses[index], model="fake")


@pytest.fixture()
def fake_client() -> type[FakeClient]:
    return FakeClient


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Point ~/.olivia at tmp_path, force offline, reset process singletons."""
    from olivia.config import settings
    from olivia.llm.client import get_client

    monkeypatch.setattr(settings, "home_dir", tmp_path / "olivia-home")
    # Paths that resolve get_client() internally must never reach a real API.
    monkeypatch.setattr(settings.llm, "provider", "none")
    cast(Any, get_client).cache_clear()
    import olivia.meta.learner as learner

    monkeypatch.setattr(learner, "_singleton", None)
    yield
    cast(Any, get_client).cache_clear()


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Any real HTTP attempt is a test bug — fail loudly."""
    import httpx

    def _blocked(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("network access attempted during tests")

    monkeypatch.setattr(httpx, "get", _blocked)
    monkeypatch.setattr(httpx, "post", _blocked)
    yield
