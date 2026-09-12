from iras.providers.openai_compatible import (
    OpenAICompatibleProvider,
)


def test_first_token_timeout_default(
    monkeypatch,
):
    monkeypatch.delenv(
        "IRAS_FIRST_TOKEN_TIMEOUT",
        raising=False,
    )

    assert (
        OpenAICompatibleProvider
        ._first_token_timeout_seconds()
        == 8.0
    )


def test_first_token_timeout_is_bounded(
    monkeypatch,
):
    monkeypatch.setenv(
        "IRAS_FIRST_TOKEN_TIMEOUT",
        "0.5",
    )

    assert (
        OpenAICompatibleProvider
        ._first_token_timeout_seconds()
        == 3.0
    )

    monkeypatch.setenv(
        "IRAS_FIRST_TOKEN_TIMEOUT",
        "999",
    )

    assert (
        OpenAICompatibleProvider
        ._first_token_timeout_seconds()
        == 30.0
    )


def test_stream_read_timeout_is_after_first_token_timeout(
    monkeypatch,
):
    monkeypatch.setenv(
        "IRAS_FIRST_TOKEN_TIMEOUT",
        "8",
    )
    monkeypatch.setenv(
        "IRAS_STREAM_READ_TIMEOUT",
        "5",
    )

    assert (
        OpenAICompatibleProvider
        ._stream_read_timeout_seconds()
        >= 9.0
    )
