from iras.core.agent import IRASAgent


def make_agent():
    agent = object.__new__(IRASAgent)
    agent.smart_tools = True
    return agent


def test_plain_open_stays_launch_only():
    agent = make_agent()
    assert agent._smart_tool_names(
        "open chrome"
    ) == [
        "device_open_app"
    ]


def test_open_and_search_uses_interaction_tool():
    agent = make_agent()
    assert agent._smart_tool_names(
        "open chrome and search youtube"
    ) == [
        "device_interact_app"
    ]


def test_type_in_notepad_uses_interaction_tool():
    agent = make_agent()
    assert agent._smart_tool_names(
        "type hello world in notepad"
    ) == [
        "device_interact_app"
    ]


def test_search_in_chrome_uses_interaction_tool():
    agent = make_agent()
    assert agent._smart_tool_names(
        "search cats in chrome"
    ) == [
        "device_interact_app"
    ]


def test_wrong_app_target_is_blocked():
    assert (
        IRASAgent._device_app_allowed(
            "search youtube in chrome",
            "chrome",
        )
        is True
    )
    assert (
        IRASAgent._device_app_allowed(
            "search youtube in chrome",
            "vscode",
        )
        is False
    )
