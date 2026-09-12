from iras.core.agent import IRASAgent
from iras.device_bridge.intent import direct_device_intent
from iras.device_bridge.planner import (
    SAFE_DEVICE_PLANNER_TOOLS,
    extract_app_scope,
    should_use_device_planner,
)


def make_agent():
    agent = object.__new__(IRASAgent)
    agent.smart_tools = True
    return agent


def test_compound_unknown_app_task_uses_planner():
    assert direct_device_intent(
        "open Discord and send hello to Hamza"
    ) is None

    agent = make_agent()
    selected = set(
        agent._smart_tool_names(
            "open Discord and send hello to Hamza"
        )
    )

    assert selected == set(
        SAFE_DEVICE_PLANNER_TOOLS
    )
    assert "device_detect_apps" in selected
    assert "device_open_app" in selected
    assert "device_interact_app" in selected


def test_new_search_in_unknown_app_uses_planner():
    agent = make_agent()
    selected = set(
        agent._smart_tool_names(
            "search Hamza in Discord"
        )
    )

    assert selected == set(
        SAFE_DEVICE_PLANNER_TOOLS
    )


def test_game_launch_can_fall_back_to_planner_without_spotify_hijack():
    assert direct_device_intent(
        "play GTA 5"
    ) is None

    assert should_use_device_planner(
        "play GTA 5"
    ) is True

    agent = make_agent()
    selected = set(
        agent._smart_tool_names(
            "play GTA 5"
        )
    )

    assert "device_detect_apps" in selected
    assert "device_open_app" in selected


def test_informational_question_does_not_execute_device_tools():
    assert should_use_device_planner(
        "how do I open Discord?"
    ) is False

    agent = make_agent()
    assert agent._smart_tool_names(
        "how do I open Discord?"
    ) == []


def test_specialized_project_router_stays_specialized():
    agent = make_agent()
    assert agent._smart_tool_names(
        "open my project in VS Code on my PC"
    ) == [
        "device_open_project"
    ]


def test_current_turn_app_scope_is_dynamic():
    assert extract_app_scope(
        "open Discord and send hello to Hamza"
    ) == [
        "Discord"
    ]

    assert IRASAgent._device_app_allowed(
        "open Discord and send hello to Hamza",
        "Discord",
    ) is True

    assert IRASAgent._device_app_allowed(
        "open Discord and send hello to Hamza",
        "Slack",
    ) is False


def test_more_natural_spotify_search_variants():
    cases = (
        "search Heeriye in Spotify",
        "search Spotify Heeriye",
        "find Heeriye on Spotify",
        "look for Heeriye in Spotify",
    )

    for command in cases:
        result = direct_device_intent(
            command
        )
        assert result is not None
        assert result["tool"] == "device_spotify_search"
        assert result["arguments"]["query"] == "Heeriye"


def test_spotify_context_allows_short_search_followup():
    result = direct_device_intent(
        "search another song",
        spotify_context=True,
    )

    assert result is not None
    assert result["tool"] == "device_spotify_search"
    assert result["arguments"]["query"] == "another song"


def test_planner_toolset_is_bounded():
    selected = set(
        SAFE_DEVICE_PLANNER_TOOLS
    )

    assert "run_shell" not in selected
    assert "launch_app" not in selected
    assert "kill_process" not in selected
    assert all(
        name.startswith("device_")
        for name in selected
    )


def test_project_scope_is_not_mistaken_for_an_app():
    assert extract_app_scope(
        "open my project in VS Code on my PC"
    ) in ([], ["code"])


def test_known_game_request_is_scoped_to_game_title():
    scope = extract_app_scope(
        "play GTA 5"
    )
    assert scope == ["GTA 5"]
