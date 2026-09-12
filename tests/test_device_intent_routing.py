from iras.core.agent import IRASAgent


def make_agent():
    agent = object.__new__(
        IRASAgent
    )
    agent.smart_tools = True
    return agent


def test_open_chrome_only_exposes_open_app():
    agent = make_agent()

    assert agent._smart_tool_names(
        "open chrome"
    ) == [
        "device_open_app"
    ]


def test_open_chrome_on_pc_only_exposes_open_app():
    agent = make_agent()

    assert agent._smart_tool_names(
        "IRAS, open Chrome on my PC"
    ) == [
        "device_open_app"
    ]


def test_open_project_only_exposes_project_tool():
    agent = make_agent()

    assert agent._smart_tool_names(
        "open my project in VS Code on my PC"
    ) == [
        "device_open_project"
    ]


def test_run_tests_only_exposes_test_tool():
    agent = make_agent()

    assert agent._smart_tool_names(
        "run the tests in my project on my PC"
    ) == [
        "device_run_tests"
    ]


def test_chrome_request_blocks_vscode_target():
    assert (
        IRASAgent._device_app_allowed(
            "open chrome",
            "chrome",
        )
        is True
    )

    assert (
        IRASAgent._device_app_allowed(
            "open chrome",
            "vscode",
        )
        is False
    )


def test_explicit_two_app_request_allows_both():
    text = (
        "open chrome and vscode "
        "on my pc"
    )

    assert (
        IRASAgent._device_app_allowed(
            text,
            "chrome",
        )
        is True
    )

    assert (
        IRASAgent._device_app_allowed(
            text,
            "visual studio code",
        )
        is True
    )
