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


def test_health_provider_status_includes_error_details():
    text = (
        ROOT
        / "src"
        / "iras"
        / "providers"
        / "multi_provider.py"
    ).read_text(encoding="utf-8")

    assert '"last_error"' in text
    assert '"failures"' in text
