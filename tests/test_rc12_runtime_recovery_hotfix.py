from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from iras.providers.provider_factory import build_multi_provider
from iras.voice.stt import Listener


def _settings():
    return SimpleNamespace(request_timeout=3.0, provider="multi", api_key="", model="openrouter/free", system_name="IRAS")


def test_multi_without_keys_starts_bounded_demo_fallback(monkeypatch):
    for key in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY", "IRAS_API_KEY", "IRAS_OLLAMA_FALLBACK"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("IRAS_MULTI_DEMO_FALLBACK", "true")
    provider = build_multi_provider(_settings())
    assert provider.configured_names() == ["demo-fallback"]


def test_stt_rejects_punctuation_and_prompt_echo():
    listener = Listener("base", 6)
    assert listener._transcript_rejection_reason(". . . . .")
    echoed = "The speaker may use English, Urdu, Roman Urdu, or code-switch between them. Preserve commands, application names, people names, and technical terms accurately."
    assert "prompt" in listener._transcript_rejection_reason(echoed).lower()
    assert listener._transcript_rejection_reason("IRAS open Chrome") == ""


def test_microphone_status_uses_one_ranked_snapshot():
    import inspect
    source = inspect.getsource(Listener.microphone_status)
    assert "ranked_input_devices" in source
    assert "select_input_device(sd)" not in source


def test_cloud_auth_source_has_paired_token_fallback():
    text = Path("src/iras/cloud_auth.py").read_text(encoding="utf-8")
    assert "api_token_protected" in text
    assert "paired-device" in text
    client = Path("src/iras/cloud_client.py").read_text(encoding="utf-8")
    assert "cloud_token_candidates" in client
    assert "HTTP 401" in client
