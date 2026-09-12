from iras.core.agent import IRASAgent


def make_agent():
    agent = object.__new__(IRASAgent)
    agent.smart_tools = True
    agent._last_device_action = None
    return agent


def test_bare_song_is_device_tool_turn():
    agent = make_agent()
    assert agent._smart_tool_names("play Majboor song") == [
        "device_spotify_play"
    ]


def test_bare_song_does_not_stream_as_chat():
    agent = make_agent()
    assert not agent.can_stream("play Majboor song")


def test_retry_replays_last_device_action():
    agent = make_agent()
    agent._last_device_action = {
        "tool": "device_spotify_play",
        "arguments": {"query": "Majboor song"},
        "kind": "spotify_play",
    }
    assert not agent.can_stream("try again")
    resolved = agent._resolve_direct_device_action("try again")
    assert resolved["tool"] == "device_spotify_play"
    assert resolved["arguments"]["query"] == "Majboor song"
