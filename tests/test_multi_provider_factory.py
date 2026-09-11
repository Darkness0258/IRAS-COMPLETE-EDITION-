from __future__ import annotations

from dataclasses import dataclass

from iras.providers.provider_factory import build_multi_provider


@dataclass
class FakeSettings:
    request_timeout: float = 10
    api_key: str = ""
    provider: str = "multi"
    model: str = "nex-agi/nex-n2.5-mini:free"
    system_name: str = "IRAS"


def _clear(monkeypatch):
    for key in (
        "GROQ_API_KEY",
        "CEREBRAS_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "OPENROUTER_API_KEY",
        "IRAS_PROVIDER_ORDER",
    ):
        monkeypatch.delenv(key, raising=False)


def test_factory_skips_missing_providers(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("CEREBRAS_API_KEY", "test")

    provider = build_multi_provider(FakeSettings())

    assert provider.configured_names() == ["groq", "cerebras"]


def test_factory_respects_order(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setenv("CEREBRAS_API_KEY", "test")
    monkeypatch.setenv("IRAS_PROVIDER_ORDER", "cerebras,groq")

    provider = build_multi_provider(FakeSettings())

    assert provider.configured_names() == ["cerebras", "groq"]
