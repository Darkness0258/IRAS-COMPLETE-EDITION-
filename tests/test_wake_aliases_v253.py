from iras.voice.conversation import (
    extract_wake_command,
    is_probable_echo,
    wake_aliases,
)


def test_default_wake_aliases_include_common_pronunciations():
    aliases = wake_aliases("IRAS")

    assert "iras" in aliases
    assert "iris" in aliases
    assert "eris" in aliases
    assert "eye ris" in aliases
    assert "ira's" in aliases
    assert "little girl" in aliases
    assert "cute" in aliases


def test_little_girl_wakes_iras():
    assert extract_wake_command(
        "little girl"
    ) == (
        True,
        "",
    )


def test_little_girl_with_command():
    assert extract_wake_command(
        "little girl, how are you?"
    ) == (
        True,
        "how are you?",
    )


def test_cute_wakes_iras():
    assert extract_wake_command(
        "cute"
    ) == (
        True,
        "",
    )


def test_cute_with_command():
    assert extract_wake_command(
        "cute tell me a joke"
    ) == (
        True,
        "tell me a joke",
    )


def test_cute_does_not_trigger_in_middle_of_normal_sentence():
    assert extract_wake_command(
        "that is cute"
    ) == (
        False,
        "",
    )


def test_iris_still_wakes_iras():
    assert extract_wake_command(
        "Iris"
    ) == (
        True,
        "",
    )


def test_wake_alias_is_not_suppressed_as_echo():
    assert not is_probable_echo(
        "cute",
        "Cute. I knew you would say that.",
    )


def test_custom_wake_word_does_not_inherit_iras_aliases():
    assert extract_wake_command(
        "cute hello",
        wake_word="Akane",
    ) == (
        False,
        "",
    )

    assert extract_wake_command(
        "Akane hello",
        wake_word="Akane",
    ) == (
        True,
        "hello",
    )
