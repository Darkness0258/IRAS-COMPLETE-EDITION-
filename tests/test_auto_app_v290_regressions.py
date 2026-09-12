import pytest

from iras.core.agent import IRASAgent
from iras.device_bridge.app_catalog import ensure_safe_app_request
from iras.device_bridge.intent import direct_device_intent
from iras.device_bridge.universal_control import UniversalWindowsController
from iras.tools.system import launch_app


def make_agent():
    agent = object.__new__(IRASAgent)
    agent.smart_tools = True
    return agent


def test_compound_open_and_search_uses_browser_interaction():
    result = direct_device_intent("open chrome and search youtube")
    assert result is not None
    assert result["tool"] == "device_interact_app"
    assert result["arguments"]["app"].lower() == "chrome"
    assert result["arguments"]["actions"] == [
        {"action": "hotkey", "keys": ["ctrl", "l"]},
        {"action": "type", "text": "youtube"},
        {"action": "press", "key": "enter"},
    ]


def test_specialized_project_routing_is_not_hijacked():
    assert direct_device_intent(
        "open my project in VS Code on my PC"
    ) is None

    agent = make_agent()
    assert agent._smart_tool_names(
        "open my project in VS Code on my PC"
    ) == ["device_open_project"]


def test_play_video_on_youtube_is_not_misread_as_resume_media():
    assert direct_device_intent("play video on YouTube") is None


def test_pause_video_on_youtube_can_still_be_transport_control():
    result = direct_device_intent("pause video on YouTube")
    assert result == {
        "tool": "device_media_control",
        "arguments": {
            "command": "pause",
            "app": "YouTube",
        },
        "kind": "media_control",
    }


@pytest.mark.parametrize(
    "name",
    [
        "powershell",
        "Anaconda PowerShell Prompt",
        "Developer Command Prompt for VS 2022",
        "Windows Terminal",
        r"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
        r"C:\\Windows\\System32\\cmd.exe",
    ],
)
def test_shell_and_admin_launch_names_are_blocked(name):
    with pytest.raises(PermissionError):
        ensure_safe_app_request(name)


def test_launch_boundary_blocks_powershell_even_without_static_executor_allowlist():
    with pytest.raises(PermissionError):
        launch_app("powershell")


def test_plain_chrome_window_is_not_assumed_to_be_media():
    assert not UniversalWindowsController._is_media_window(
        {
            "process": "chrome.exe",
            "title": "IRAS Build Watch - Google Chrome",
        }
    )


def test_youtube_browser_window_is_media_candidate():
    assert UniversalWindowsController._is_media_window(
        {
            "process": "chrome.exe",
            "title": "YouTube - Google Chrome",
        }
    )


def test_spotify_window_is_media_candidate():
    assert UniversalWindowsController._is_media_window(
        {
            "process": "spotify.exe",
            "title": "Spotify",
        }
    )


def controller_for_unit_test():
    controller = object.__new__(UniversalWindowsController)
    controller._last_media_app = None
    return controller


def test_pause_explicit_non_running_app_is_safe_noop(monkeypatch):
    controller = controller_for_unit_test()
    monkeypatch.setattr(
        controller,
        "_auto_media_target",
        lambda app=None: (None, "Spotify"),
    )

    result = controller.media_control("pause", app="Spotify")
    assert result["already_inactive"] is True
    assert result["command_sent"] is False
    assert result["target_running"] is False


def test_stop_explicit_non_running_app_is_safe_noop(monkeypatch):
    controller = controller_for_unit_test()
    monkeypatch.setattr(
        controller,
        "_auto_media_target",
        lambda app=None: (None, "VLC media player"),
    )

    result = controller.media_control("stop", app="VLC")
    assert result["already_inactive"] is True
    assert result["command_sent"] is False
    assert result["target_running"] is False


def test_targeted_stop_sends_stop_plus_idempotent_pause(monkeypatch):
    controller = controller_for_unit_test()
    calls = []

    monkeypatch.setattr(
        controller,
        "_auto_media_target",
        lambda app=None: (123, "spotify"),
    )
    monkeypatch.setattr(
        controller,
        "_send_media_appcommand",
        lambda command_id, hwnd=None: calls.append((command_id, hwnd)) or True,
    )
    monkeypatch.setattr(
        controller,
        "_send_global_media_key",
        lambda action: (_ for _ in ()).throw(
            AssertionError("targeted stop must not hit an unrelated global session")
        ),
    )

    result = controller.media_control("stop", app="Spotify")
    assert calls == [(13, 123), (47, 123)]
    assert "wm_appcommand_pause" in result["transport"]


def test_generic_stop_without_detected_window_uses_global_stop(monkeypatch):
    controller = controller_for_unit_test()
    calls = []

    monkeypatch.setattr(
        controller,
        "_auto_media_target",
        lambda app=None: (None, None),
    )
    monkeypatch.setattr(
        controller,
        "_send_global_media_key",
        lambda action: calls.append(action) or True,
    )

    result = controller.media_control("stop")
    assert calls == ["stop"]
    assert result["transport"] == ["global_stop"]
    assert result["target_app"] is None
