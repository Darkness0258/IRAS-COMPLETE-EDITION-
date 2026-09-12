import pytest

from iras.device_bridge.intent import direct_device_intent


@pytest.mark.parametrize(
    ("text", "tool", "arguments"),
    [
        (
            "open Discord",
            "device_open_app",
            {"app": "Discord"},
        ),
        (
            "launch VLC",
            "device_open_app",
            {"app": "VLC"},
        ),
        (
            "close WhatsApp",
            "device_app_control",
            {"app": "WhatsApp", "action": "close"},
        ),
        (
            "minimize Telegram",
            "device_app_control",
            {"app": "Telegram", "action": "minimize"},
        ),
        (
            "maximize Discord",
            "device_app_control",
            {"app": "Discord", "action": "maximize"},
        ),
        (
            "focus VLC",
            "device_app_control",
            {"app": "VLC", "action": "focus"},
        ),
        (
            "pause music in VLC",
            "device_media_control",
            {"command": "pause", "app": "VLC"},
        ),
        (
            "stop music in Spotify",
            "device_media_control",
            {"command": "stop", "app": "Spotify"},
        ),
        (
            "type hello there in Discord",
            "device_interact_app",
            {
                "app": "Discord",
                "actions": [{"action": "type", "text": "hello there"}],
                "ensure_open": True,
            },
        ),
        (
            "scroll down in Telegram",
            "device_interact_app",
            {
                "app": "Telegram",
                "actions": [{"action": "scroll", "amount": -3}],
                "ensure_open": True,
            },
        ),
        (
            "search OpenAI in Edge",
            "device_interact_app",
            {
                "app": "Edge",
                "actions": [
                    {"action": "hotkey", "keys": ["ctrl", "l"]},
                    {"action": "type", "text": "OpenAI"},
                    {"action": "press", "key": "enter"},
                ],
                "ensure_open": True,
            },
        ),
    ],
)
def test_auto_app_commands(text, tool, arguments):
    result = direct_device_intent(text)
    assert result is not None
    assert result["tool"] == tool
    assert result["arguments"] == arguments


def test_app_discovery_intent():
    result = direct_device_intent("what apps are installed")
    assert result["tool"] == "device_detect_apps"


def test_existing_spotify_music_routing_is_preserved():
    result = direct_device_intent("play Believer")
    assert result["tool"] == "device_spotify_play"
    assert result["arguments"]["query"] == "Believer"


def test_open_spotify_preserves_old_open_app_contract():
    result = direct_device_intent("open Spotify")
    assert result == {
        "tool": "device_open_app",
        "arguments": {"app": "spotify"},
        "kind": "spotify_open",
    }
