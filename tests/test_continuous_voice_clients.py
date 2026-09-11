from pathlib import Path

ROOT = Path(
    __file__
).resolve().parents[1]

def test_web_has_continuous_wake_word_mode():
    text = (
        ROOT
        / "clients"
        / "web"
        / "index.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Hands-free On" in text
    assert "r.continuous=true" in text
    assert "conversationUntil" in text
    assert "probableEcho" in text

def test_android_has_foreground_handsfree_mode():
    text = (
        ROOT
        / "clients"
        / "android"
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "darkness"
        / "iras"
        / "MainActivity.java"
    ).read_text(
        encoding="utf-8"
    )

    assert "Hands-free On" in text
    assert "startHandsFreeListening" in text
    assert "conversationUntil" in text
    assert "probableEcho" in text

def test_windows_has_barge_in_and_vad():
    desktop = (
        ROOT
        / "src"
        / "iras"
        / "remote_desktop.py"
    ).read_text(
        encoding="utf-8"
    )

    stt = (
        ROOT
        / "src"
        / "iras"
        / "voice"
        / "stt.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "_handsfree_worker" in desktop
    assert "speaker.stop()" in desktop
    assert "listen_phrase" in stt
    assert "silence_seconds" in stt
