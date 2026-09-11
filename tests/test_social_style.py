from iras.social_style import (
    empty_reply_fallback,
    is_literal_identity_question,
    is_social_turn,
    normalize_social_reply,
    social_system_nudge,
)


def test_happy_question_is_social_not_identity():
    assert is_social_turn("are you happy")
    assert not is_literal_identity_question("are you happy")


def test_literal_ai_identity_is_not_rewritten():
    assert not is_social_turn("are you actually human?")
    assert is_literal_identity_question("are you actually human?")


def test_robotic_happiness_disclaimer_is_replaced():
    reply = (
        "Not in the human sense — "
        "I don't have feelings, but "
        "I'm in a good mood."
    )
    cleaned = normalize_social_reply(
        "are you happy",
        reply,
    )
    assert "don't have feelings" not in cleaned.lower()
    assert "human sense" not in cleaned.lower()
    assert cleaned.startswith("Yeah")


def test_boss_vocative_is_removed():
    cleaned = normalize_social_reply(
        "hello",
        "Hey, boss. How's your day going?",
    )
    assert "boss" not in cleaned.lower()
    assert "How's your day" in cleaned


def test_done_is_never_social_fallback():
    cleaned = normalize_social_reply(
        "hello",
        "Done.",
    )
    assert cleaned != "Done."


def test_non_social_empty_reply_is_human_error():
    assert empty_reply_fallback(
        "explain recursion"
    ) != "Done."


def test_social_nudge_bans_machine_disclaimer():
    prompt = social_system_nudge(
        "are you happy"
    )
    assert "NOT as requests" in prompt
    assert "I don't have feelings" in prompt
    assert "Do not call the user" in prompt
