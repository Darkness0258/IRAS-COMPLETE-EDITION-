import pytest

from iras.device_bridge.ui_control import (
    WindowsUIController,
)


def test_media_codes_are_allowlisted():
    assert (
        WindowsUIController
        .MEDIA_KEY_CODES[
            "play_pause"
        ]
        == 0xB3
    )
    assert (
        WindowsUIController
        .MEDIA_KEY_CODES[
            "next"
        ]
        == 0xB0
    )


def test_spotify_query_length_guard_without_windows():
    controller = WindowsUIController()

    with pytest.raises(
        PermissionError,
    ):
        controller.spotify_play(
            "x" * 221
        )


def test_media_unknown_command_is_rejected_before_windows_call():
    controller = WindowsUIController()

    with pytest.raises(
        PermissionError,
    ):
        controller.media_control(
            "launch missiles"
        )
