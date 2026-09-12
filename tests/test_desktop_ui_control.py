import pytest

from iras.device_bridge.ui_control import (
    WindowsUIController,
)


def test_valid_keyboard_sequence():
    actions = (
        WindowsUIController
        .validate_actions(
            [
                {
                    "action": "hotkey",
                    "keys": [
                        "ctrl",
                        "l",
                    ],
                },
                {
                    "action": "type",
                    "text": "youtube.com",
                },
                {
                    "action": "press",
                    "key": "enter",
                },
            ]
        )
    )

    assert [
        item["action"]
        for item in actions
    ] == [
        "hotkey",
        "type",
        "press",
    ]


def test_windows_key_is_blocked():
    with pytest.raises(PermissionError):
        WindowsUIController.validate_actions(
            [
                {
                    "action": "hotkey",
                    "keys": ["win", "r"],
                }
            ]
        )


def test_alt_f4_is_blocked():
    with pytest.raises(PermissionError):
        WindowsUIController.validate_actions(
            [
                {
                    "action": "hotkey",
                    "keys": ["alt", "f4"],
                }
            ]
        )


def test_unknown_action_is_blocked():
    with pytest.raises(PermissionError):
        WindowsUIController.validate_actions(
            [
                {
                    "action": "shell",
                    "command": "whoami",
                }
            ]
        )


def test_supported_app_aliases():
    assert (
        WindowsUIController
        .canonical_app("VS Code")
        == "code"
    )
    assert (
        WindowsUIController
        .canonical_app("Google Chrome")
        == "chrome"
    )
