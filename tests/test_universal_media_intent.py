import pytest

from iras.device_bridge.intent import (
    direct_device_intent,
    is_retry_phrase,
)


@pytest.mark.parametrize(
    ("text", "tool", "key", "value"),
    [
        ("play Believer", "device_spotify_play", "query", "Believer"),
        ("play Shape of You", "device_spotify_play", "query", "Shape of You"),
        ("play Heeriye song", "device_spotify_play", "query", "Heeriye song"),
        ("put on Pasoori", "device_spotify_play", "query", "Pasoori"),
        ("listen to Afusic", "device_spotify_play", "query", "Afusic"),
        ("search Spotify for Atif Aslam", "device_spotify_search", "query", "Atif Aslam"),
        ("pause", "device_media_control", "command", "pause"),
        ("resume", "device_media_control", "command", "play"),
        ("next song", "device_media_control", "command", "next"),
        ("previous song", "device_media_control", "command", "previous"),
        ("shuffle", "device_media_control", "command", "shuffle_toggle"),
        ("repeat mode", "device_media_control", "command", "repeat_toggle"),
        ("open queue", "device_media_control", "command", "open_queue"),
        ("open Spotify", "device_open_app", "app", "spotify"),
    ],
)
def test_universal_media_routes(text, tool, key, value):
    result = direct_device_intent(text)
    assert result is not None
    assert result["tool"] == tool
    assert result["arguments"][key] == value


@pytest.mark.parametrize(
    "text",
    [
        "play game Valorant",
        "play video on YouTube",
        "play movie on Netflix",
    ],
)
def test_non_music_destinations_are_not_hijacked(text):
    assert direct_device_intent(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "try again",
        "retry",
        "do that again",
        "same song again",
        "play it again",
    ],
)
def test_retry_phrases(text):
    assert is_retry_phrase(text)
