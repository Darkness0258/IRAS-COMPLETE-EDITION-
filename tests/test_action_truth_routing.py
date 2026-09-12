from iras.core.agent import IRASAgent


def make_agent():
    agent = object.__new__(IRASAgent)
    agent.smart_tools = True
    return agent


def test_spotify_play_routes_to_dedicated_tool():
    agent = make_agent()
    assert agent._smart_tool_names(
        "open Spotify and play Majboor song"
    ) == [
        "device_spotify_play"
    ]


def test_play_song_followup_routes_to_media_control():
    agent = make_agent()
    assert agent._smart_tool_names(
        "play the song"
    ) == [
        "device_media_control"
    ]


def test_pause_song_followup_routes_to_media_control():
    agent = make_agent()
    assert agent._smart_tool_names(
        "pause the song"
    ) == [
        "device_media_control"
    ]


def test_plain_spotify_open_stays_launch_only():
    agent = make_agent()
    assert agent._smart_tool_names(
        "open spotify"
    ) == [
        "device_open_app"
    ]
