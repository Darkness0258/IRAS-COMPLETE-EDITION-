from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_factory_uses_gemini_adapter():
    text = (
        ROOT
        / "src"
        / "iras"
        / "providers"
        / "provider_factory.py"
    ).read_text(encoding="utf-8")

    assert "GeminiOpenAICompatibleProvider" in text


def test_public_provider_status_stays_minimal():
    from iras.providers.multi_provider import (
        MultiProvider,
        ProviderSlot,
    )

    class DummyProvider:
        model = "dummy/model"

    provider = MultiProvider(
        [
            ProviderSlot(
                "dummy",
                DummyProvider(),
            )
        ]
    )

    assert provider.status() == [
        {
            "name": "dummy",
            "model": "dummy/model",
            "ready": True,
            "cooldown_seconds": 0,
        }
    ]
