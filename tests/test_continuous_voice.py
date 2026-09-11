from iras.voice.conversation import (
    extract_wake_command,
    is_probable_echo,
    pop_complete_sentences,
)

def test_wake_word_only():
    assert extract_wake_command(
        "IRAS"
    ) == (
        True,
        "",
    )

def test_wake_word_with_command():
    assert extract_wake_command(
        "Hey IRAS, open VS Code"
    ) == (
        True,
        "open VS Code",
    )

def test_followup_window_accepts_without_wake_word():
    assert extract_wake_command(
        "and open the project",
        armed=True,
    ) == (
        True,
        "and open the project",
    )

def test_sleeping_mode_ignores_unaddressed_speech():
    assert extract_wake_command(
        "open VS Code",
        armed=False,
    ) == (
        False,
        "",
    )

def test_echo_filter_detects_spoken_sentence():
    assert is_probable_echo(
        "good to see you back",
        "Hey, good to see you back.",
    )

def test_echo_filter_never_blocks_standalone_wake_word():
    assert not is_probable_echo(
        "IRAS",
        "IRAS is speaking right now.",
    )

def test_streaming_sentence_chunks():
    sentences, rest = (
        pop_complete_sentences(
            "Hello there. How are"
        )
    )
    assert sentences == [
        "Hello there."
    ]
    assert rest == "How are"

    sentences, rest = (
        pop_complete_sentences(
            rest,
            force=True,
        )
    )
    assert sentences == [
        "How are"
    ]
    assert rest == ""
