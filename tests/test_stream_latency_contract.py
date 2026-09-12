from pathlib import Path


ROOT = Path(
    __file__
).resolve().parents[1]


def test_stream_has_first_token_timeout():
    text = (
        ROOT
        / "src"
        / "iras"
        / "providers"
        / "openai_compatible.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "IRAS_FIRST_TOKEN_TIMEOUT" in text
    assert "timed out waiting for first token" in text
    assert "timeout=request_timeout" in text


def test_chat_lock_is_bounded():
    text = (
        ROOT
        / "src"
        / "iras"
        / "cloud_api.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "IRAS_CHAT_LOCK_TIMEOUT" in text
    assert "timeout=lock_wait" in text
