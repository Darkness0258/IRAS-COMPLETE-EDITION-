from iras.social_style import (
    is_literal_identity_question,
    is_social_turn,
    needs_buffered_social_guard,
    normalize_social_reply,
    sanitize_stream_chunk,
)


def test_actually_human_is_literal_identity_question():
    assert is_literal_identity_question(
        "are you actually human?"
    )


def test_really_ai_is_literal_identity_question():
    assert is_literal_identity_question(
        "are you really an AI?"
    )


def test_happy_is_social_and_buffered():
    assert is_social_turn(
        "are you happy"
    )
    assert needs_buffered_social_guard(
        "are you happy"
    )


def test_plain_hello_remains_true_streaming():
    assert is_social_turn(
        "hello"
    )
    assert not needs_buffered_social_guard(
        "hello"
    )


def test_robotic_happy_reply_is_replaced():
    cleaned = normalize_social_reply(
        "are you happy",
        (
            "Not in the human sense — "
            "I don't have feelings, but "
            "I'm doing fine."
        ),
    )

    assert "human sense" not in (
        cleaned.lower()
    )
    assert "don't have feelings" not in (
        cleaned.lower()
    )


def test_stream_chunk_preserves_boss_vocative():
    assert sanitize_stream_chunk(
        "Hey, boss. "
    ) == "Hey, boss. "
