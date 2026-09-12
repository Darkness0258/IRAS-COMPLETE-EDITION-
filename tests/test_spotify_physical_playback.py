from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_spotify_uses_physical_window_coordinates():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "ui_control.py"
    ).read_text(encoding="utf-8")

    assert "DwmGetWindowAttribute" in text
    assert "DWMWA_EXTENDED_FRAME_BOUNDS" in text
    assert "SetPhysicalCursorPos" in text
    assert "GetPhysicalCursorPos" in text


def test_spotify_sends_explicit_play_not_toggle():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "ui_control.py"
    ).read_text(encoding="utf-8")

    assert "APPCOMMAND_MEDIA_PLAY = 46" in text
    assert "SendMessageTimeoutW" in text


def test_spotify_diagnostics_include_cursor_and_media_play():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "ui_control.py"
    ).read_text(encoding="utf-8")

    assert "cursor_actual=" in text
    assert "media_play=" in text
