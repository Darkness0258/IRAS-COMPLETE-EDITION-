from iras.voice.humanize import speech_text


def test_removes_emoji_without_speaking_name():
    assert speech_text("Nice work 😌❤️") == "Nice work"


def test_removes_markdown_emphasis_and_heading():
    out = speech_text("# **Done**\n- Everything is working.")
    assert out == "Done\nEverything is working."


def test_markdown_link_keeps_label_not_url():
    out = speech_text("Open [the docs](https://example.com/docs) when you need them.")
    assert "the docs" in out
    assert "https://" not in out
    assert "example.com" not in out


def test_raw_url_is_not_read():
    out = speech_text("I found it at https://example.com/a?x=1")
    assert "https" not in out
    assert "example.com" not in out


def test_inline_code_loses_backticks():
    assert speech_text("Run `iras --voice-test`.") == "Run iras --voice-test."


def test_code_block_is_not_read_character_by_character():
    out = speech_text("```python\nprint('hello')\n```")
    assert out == "I put the code on screen."


def test_arrow_becomes_natural_word():
    assert speech_text("Mic → Whisper → IRAS") == "Mic to Whisper to IRAS"


def test_stage_markdown_symbol_does_not_leak():
    out = speech_text("*smiles* hello")
    assert "*" not in out
