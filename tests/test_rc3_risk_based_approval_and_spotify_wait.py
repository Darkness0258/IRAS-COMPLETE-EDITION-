from __future__ import annotations

from iras.device_bridge.local_store import LocalDeviceBridgeStore
from iras.device_bridge.tools import make_tools
from iras.device_bridge.remote_context import remote_command_context
from iras.device_bridge.ui_control import WindowsUIController
from iras.models import PermissionLevel


class _FakeExecutor:
    def execute(self, action, arguments):
        return {"action": action, "arguments": dict(arguments)}


class _RemoteLikeStore:
    def list_devices(self):
        return []

    def request_and_wait(self, **kwargs):
        return kwargs


def _tool_map(store):
    return {tool.name: tool for tool in make_tools(store)}


def test_local_routine_media_actions_do_not_prompt_but_risky_ui_still_does():
    tools = _tool_map(LocalDeviceBridgeStore(_FakeExecutor()))

    assert tools["device_spotify_search"].required_permission({"query": "naat"}) == PermissionLevel.SAFE_ACTION
    assert tools["device_spotify_play"].required_permission({"query": "naat"}) == PermissionLevel.SAFE_ACTION
    assert tools["device_media_control"].required_permission({"command": "pause", "app": "spotify"}) == PermissionLevel.SAFE_ACTION
    assert tools["device_whatsapp_open_chat"].required_permission({"contact": "Alice"}) == PermissionLevel.SAFE_ACTION
    assert tools["device_ui_scroll_until_text"].required_permission({"text": "Settings"}) == PermissionLevel.SAFE_ACTION

    # Generic state-changing UI still requires approval because it can click,
    # type, submit, or otherwise affect an arbitrary application state.
    assert tools["device_interact_app"].required_permission({"app": "chrome", "actions": [{"action": "press", "key": "enter"}]}) == PermissionLevel.SYSTEM_ACTION
    assert tools["device_ui_click_text"].required_permission({"text": "Delete"}) == PermissionLevel.SYSTEM_ACTION


def test_cloud_routine_media_actions_are_safe_but_remote_enforcement_stays_strict():
    store = _RemoteLikeStore()
    tools = _tool_map(store)

    # Cloud/Web/Android should not prompt for bounded routine media actions.
    assert tools["device_spotify_play"].required_permission({"query": "naat"}) == PermissionLevel.SAFE_ACTION
    assert tools["device_media_control"].required_permission({"command": "pause", "app": "spotify"}) == PermissionLevel.SAFE_ACTION
    assert tools["device_whatsapp_open_chat"].required_permission({"contact": "Alice"}) == PermissionLevel.SAFE_ACTION

    # Risky generic UI remains approval-gated.
    assert tools["device_ui_click_text"].required_permission({"text": "Delete"}) == PermissionLevel.SYSTEM_ACTION
    assert tools["device_ui_type_text"].required_permission({"target": "Message", "text": "send this"}) == PermissionLevel.SYSTEM_ACTION

    # The queue still carries the original Remote permission level. Lowering
    # the prompt classification must not weaken the device authorization layer.
    with remote_command_context({
        "session_id": "session-test",
        "device_id": "device-test",
        "requester_device": "web-test",
    }):
        result = tools["device_spotify_play"].handler(query="naat")
    assert result["remote_session_id"] == "session-test"
    assert result["permission_level"] == int(PermissionLevel.SYSTEM_ACTION)


class _SpotifySequenceController(WindowsUIController):
    def __init__(self):
        self.events = []

    def focus_app(self, app, *, ensure_open=True):
        self.events.append("open_and_focus")
        return {"app": "spotify", "window": 77, "launched": True, "foreground_verified": True}

    def _wait_for_spotify_ui_ready(self, hwnd, **kwargs):
        self.events.append("wait:" + str(kwargs.get("phase")))
        return {"ready": True, "waited_ms": 1500}

    def _open_spotify_search_uri(self, query):
        self.events.append("uri_search:" + query)
        return True

    def _spotify_find_query_results(self, hwnd, query, *, limit=4):
        self.events.append("find_results")
        return [{
            "name": "Heart touching naat sharif",
            "role": "ListItem",
            "enabled": True,
            "rect": {"left": 400, "top": 200, "width": 200, "height": 50},
            "match_score": 10.0,
        }]

    def _invoke_spotify_observed_element(self, hwnd, element):
        self.events.append("select_result")
        return {"name": element.get("name", ""), "invoked": True}

    def _dismiss_spotify_quick_search_overlay(self, hwnd):
        return {"present_before": False, "dismissed": True, "attempts": 0}

    def _wait_for_spotify_playback(self, hwnd, query, *, timeout=5.0):
        self.events.append("verify")
        return {
            "verified": True,
            "playing": True,
            "query_match": True,
            "spotify_error": None,
            "query_evidence": ["Heart touching naat sharif"],
            "now_playing_candidates": ["Heart touching naat sharif", "Nabi Un Nabi"],
        }


def test_spotify_play_waits_then_selects_real_result_before_reporting_playback():
    controller = _SpotifySequenceController()
    result = controller.spotify_play("naat")

    assert result["command_sent"] is True
    assert result["verified_playback"] is True
    assert controller.events.index("open_and_focus") < controller.events.index("wait:startup")
    assert controller.events.index("wait:startup") < controller.events.index("uri_search:naat")
    assert controller.events.index("uri_search:naat") < controller.events.index("wait:uri_search_results")
    assert controller.events.index("wait:uri_search_results") < controller.events.index("find_results")
    assert controller.events.index("find_results") < controller.events.index("select_result")
    assert controller.events.index("select_result") < controller.events.index("verify")


def test_omniparser_repair_reuses_live_florence_assets_instead_of_rmtree():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    text = (root / "setup-omniparser.ps1").read_text(encoding="utf-8")
    assert 'Reusing existing Florence asset:' in text
    assert 'shutil.rmtree(dst)' not in text
    assert 'shutil.copy2(downloaded, target)' in text
