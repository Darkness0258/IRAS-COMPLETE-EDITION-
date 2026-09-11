from iras.social_style import (
    normalize_social_reply,
    requested_title,
    sanitize_stream_chunk,
)


def test_boss_is_allowed_and_detected():
    assert requested_title(
        "call me boss"
    ) == "boss"


def test_sir_is_allowed_and_detected():
    assert requested_title(
        "refer to me as sir"
    ) == "sir"


def test_master_is_allowed_and_detected():
    assert requested_title(
        "you can call me master"
    ) == "master"


def test_boss_is_not_stripped_from_reply():
    reply = normalize_social_reply(
        "call me boss",
        "You got it, boss.",
    )

    assert reply == "You got it, boss."


def test_stream_sanitizer_keeps_title():
    assert sanitize_stream_chunk(
        "Hey, boss."
    ) == "Hey, boss."
