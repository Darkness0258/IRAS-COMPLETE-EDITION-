from pathlib import Path

from iras.device_bridge.intent import spotify_query_from_text

ROOT = Path(__file__).resolve().parents[1]


def test_spotify_focus_is_verified():
    text = (
        ROOT / "src" / "iras" / "device_bridge" / "ui_control.py"
    ).read_text(encoding="utf-8")

    assert "def _force_foreground(" in text
    assert "GetForegroundWindow" in text
    assert "AttachThreadInput" in text
    assert "foreground_verified" in text


def test_spotify_has_uri_search_fallback():
    text = (
        ROOT / "src" / "iras" / "device_bridge" / "ui_control.py"
    ).read_text(encoding="utf-8")

    assert "spotify:search:" in text
    assert "ShellExecuteW" in text
    assert "deep_link_opened" in text


def test_voice_yah_song_normalizes():
    assert spotify_query_from_text("yah majbur song") == "majbur song"


def test_non_music_yah_is_not_spotify():
    assert spotify_query_from_text("yah open chrome") is None
