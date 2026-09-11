from __future__ import annotations

import pytest

from iras.models import ProviderReply
from iras.providers.openrouter import OpenRouterProvider


def _provider():
    return OpenRouterProvider(
        api_key="test-key",
        model="primary/free",
        fallback_models=[
            "fallback/free",
            "openrouter/free",
        ],
    )


def test_429_is_retryable():
    p = _provider()
    assert p._retryable_error(
        RuntimeError(
            "LLM HTTP 429: rate limit reached."
        )
    )


def test_401_is_not_retryable():
    p = _provider()
    assert not p._retryable_error(
        RuntimeError(
            "LLM HTTP 401: API key is invalid."
        )
    )


def test_fallback_after_rate_limit(monkeypatch):
    p = _provider()
    attempted = []

    class FakeProvider:
        def __init__(self, model):
            self.model = model

        def complete(self, messages, tools):
            attempted.append(self.model)

            if self.model == "primary/free":
                raise RuntimeError(
                    "LLM HTTP 429: rate limit reached."
                )

            return ProviderReply(
                "ok",
                [],
                {"content": "ok"},
            )

    monkeypatch.setattr(
        p,
        "_provider_for_model",
        lambda model: FakeProvider(model),
    )

    result = p.complete([], [])

    assert result.text == "ok"
    assert attempted == [
        "primary/free",
        "fallback/free",
    ]
    assert p.last_model == "fallback/free"


def test_does_not_fallback_on_auth_error(monkeypatch):
    p = _provider()
    attempted = []

    class FakeProvider:
        def __init__(self, model):
            self.model = model

        def complete(self, messages, tools):
            attempted.append(self.model)
            raise RuntimeError(
                "LLM HTTP 401: API key is invalid."
            )

    monkeypatch.setattr(
        p,
        "_provider_for_model",
        lambda model: FakeProvider(model),
    )

    with pytest.raises(
        RuntimeError,
        match="401",
    ):
        p.complete([], [])

    assert attempted == ["primary/free"]
