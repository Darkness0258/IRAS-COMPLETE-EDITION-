from pathlib import Path

from PIL import Image, ImageDraw

from iras.device_bridge.ui_control import (
    WindowsUIController,
)


ROOT = Path(__file__).resolve().parents[1]


def test_green_component_detector_prefers_large_button():
    image = Image.new(
        "RGB",
        (900, 300),
        (20, 20, 20),
    )

    draw = ImageDraw.Draw(
        image
    )

    draw.ellipse(
        (700, 60, 750, 110),
        fill=(30, 215, 96),
    )

    draw.ellipse(
        (200, 180, 210, 190),
        fill=(30, 215, 96),
    )

    components = (
        WindowsUIController
        ._spotify_green_components(
            image
        )
    )

    large = [
        component
        for component in components
        if (
            component["green_pixels"]
            >= 350
            and component["width"]
            >= 24
            and component["height"]
            >= 24
        )
    ]

    assert len(large) == 1
    assert large[0]["width"] >= 45
    assert large[0]["height"] >= 45


def test_spotify_click_has_no_guess_or_media_play_fallback():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "ui_control.py"
    ).read_text(
        encoding="utf-8"
    )

    start = text.index(
        "    def _click_spotify_play_button("
    )
    end = text.index(
        "    def spotify_search(",
        start,
    )

    block = text[start:end]

    assert "_wait_for_spotify_play_button" in block
    assert "* 0.69" not in block
    assert "* 0.21" not in block
    assert "_send_spotify_play_command" not in block


def test_spotify_waits_for_rendered_results():
    text = (
        ROOT
        / "src"
        / "iras"
        / "device_bridge"
        / "ui_control.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "def _wait_for_spotify_play_button(" in text
    assert "timeout=8.0" in text
    assert "detection_attempts" in text
