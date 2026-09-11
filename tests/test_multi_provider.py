from __future__ import annotations

import pytest

from iras.models import ProviderReply
from iras.providers.multi_provider import MultiProvider, ProviderSlot


class FakeProvider:
    def __init__(self, model, *, error=None, chunks=None):
        self.model = model
        self.last_model = model
        self.last_response_model = model
        self.last_request_ms = 5
        self.last_first_token_ms = 2
        self.error = error
        self.chunks = list(chunks) if chunks is not None else ["ok"]
        self.complete_calls = 0
        self.stream_calls = 0

    def complete(self, messages, tools):
        self.complete_calls += 1
        if self.error:
            raise RuntimeError(self.error)
        return ProviderReply(
            "ok",
            [],
            {"role": "assistant", "content": "ok"},
        )

    def stream_text(self, messages, tools):
        self.stream_calls += 1
        if self.error:
            raise RuntimeError(self.error)
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def close(self):
        pass


def test_complete_fails_over_between_providers():
    groq = FakeProvider("groq-model", error="LLM HTTP 429: rate limit reached.")
    cerebras = FakeProvider("cerebras-model")
    provider = MultiProvider([
        ProviderSlot("groq", groq),
        ProviderSlot("cerebras", cerebras),
    ])

    reply = provider.complete([], [])

    assert reply.text == "ok"
    assert provider.last_provider == "cerebras"
    assert groq.complete_calls == 1
    assert cerebras.complete_calls == 1


def test_provider_auth_failure_does_not_kill_pool():
    groq = FakeProvider("groq-model", error="LLM HTTP 401: API key is invalid.")
    gemini = FakeProvider("gemini-model")
    provider = MultiProvider([
        ProviderSlot("groq", groq),
        ProviderSlot("gemini", gemini),
    ])

    assert provider.complete([], []).text == "ok"
    assert provider.last_provider == "gemini"


def test_stream_falls_back_before_first_token():
    groq = FakeProvider("groq-model", error="LLM HTTP 503: unavailable.")
    cloudflare = FakeProvider("cf-model", chunks=["hello", " world"])
    provider = MultiProvider([
        ProviderSlot("groq", groq),
        ProviderSlot("cloudflare", cloudflare),
    ])

    assert "".join(provider.stream_text([], [])) == "hello world"
    assert provider.last_provider == "cloudflare"


def test_stream_never_switches_after_output_started():
    first = FakeProvider(
        "first-model",
        chunks=["partial", RuntimeError("LLM HTTP 503: failed")],
    )
    second = FakeProvider("second-model", chunks=["replacement"])
    provider = MultiProvider([
        ProviderSlot("first", first),
        ProviderSlot("second", second),
    ])

    stream = provider.stream_text([], [])
    assert next(stream) == "partial"
    with pytest.raises(RuntimeError, match="503"):
        next(stream)
    assert second.stream_calls == 0


def test_failed_provider_enters_cooldown():
    bad = FakeProvider("bad", error="LLM HTTP 429: rate limit reached.")
    good = FakeProvider("good")
    provider = MultiProvider([
        ProviderSlot("bad", bad),
        ProviderSlot("good", good),
    ], cooldown_seconds=60)

    provider.complete([], [])
    provider.complete([], [])

    assert bad.complete_calls == 1
    assert good.complete_calls == 2


def test_status_contains_no_credentials():
    provider = MultiProvider([
        ProviderSlot("groq", FakeProvider("qwen/test")),
    ])

    assert provider.status() == [
        {
            "name": "groq",
            "model": "qwen/test",
            "ready": True,
            "cooldown_seconds": 0,
        }
    ]
