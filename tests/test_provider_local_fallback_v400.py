from __future__ import annotations

from types import SimpleNamespace

from iras.providers.provider_factory import build_multi_provider


def test_multi_provider_can_include_local_ollama_last(monkeypatch):
    for key in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("IRAS_OLLAMA_FALLBACK", "true")
    monkeypatch.setenv("IRAS_PROVIDER_ORDER", "ollama")
    settings = SimpleNamespace(
        request_timeout=3.0,
        provider="multi",
        api_key="",
        model="openrouter/free",
        system_name="IRAS",
    )
    provider = build_multi_provider(settings)
    status = provider.status()
    assert status[0]["name"] == "ollama"
