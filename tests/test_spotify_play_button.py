from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_spotify_uses_real_play_button_click():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "ui_control.py"
    ).read_text(encoding="utf-8")

    assert "def _spotify_play_button_point(" in text
    assert "ImageGrab.grab(" in text
    assert "green_pixels" in text
    assert "def _click_spotify_play_button(" in text
    assert '"play_button_clicked": True' in text


def test_spotify_no_longer_assumes_down_enter_is_play():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "ui_control.py"
    ).read_text(encoding="utf-8")

    start = text.index(
        "    def spotify_play("
    )
    end = text.index(
        "    def media_control(",
        start,
    )

    block = text[start:end]

    assert 'self.press(\\n            "down"' not in block
    assert "_click_spotify_play_button" in block


def test_spotify_click_keeps_foreground_guard():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "ui_control.py"
    ).read_text(encoding="utf-8")

    start = text.index(
        "    def _click_spotify_play_button("
    )
    end = text.index(
        "    def spotify_play(",
        start,
    )

    block = text[start:end]

    assert "_force_foreground" in block
    assert "_set_physical_cursor" in block
    assert "mouse_event" in block
