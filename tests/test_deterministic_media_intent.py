from iras.device_bridge.intent import (
    direct_device_intent,
    is_retry_phrase,
    spotify_query_from_text,
)


def test_bare_song_request_routes_to_spotify():
    assert direct_device_intent("play Majboor song") == {
        "tool": "device_spotify_play",
        "arguments": {"query": "Majboor song"},
        "kind": "spotify_play",
    }


def test_explicit_spotify_request_routes_to_spotify():
    result = direct_device_intent("open Spotify and play Majboor")
    assert result["tool"] == "device_spotify_play"
    assert result["arguments"]["query"] == "Majboor"


def test_generic_play_song_is_media_command():
    assert direct_device_intent("play the song") == {
        "tool": "device_media_control",
        "arguments": {"command": "play"},
        "kind": "media_control",
    }


def test_non_music_play_is_not_hijacked():
    assert spotify_query_from_text("play GTA 5") is None


def test_retry_phrases():
    assert is_retry_phrase("try again")
    assert is_retry_phrase("do it again")
