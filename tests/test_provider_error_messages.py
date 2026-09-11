from iras.providers.openai_compatible import (
    OpenAICompatibleProvider,
)


def test_http_402_error_is_provider_neutral():
    error = (
        OpenAICompatibleProvider
        ._runtime_http_error(
            402,
            "quota exhausted",
        )
    )

    text = str(error)

    assert "LLM HTTP 402" in text
    assert "quota exhausted" in text
    assert "OpenRouter account" not in text
