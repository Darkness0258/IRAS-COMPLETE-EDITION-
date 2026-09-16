from __future__ import annotations

from iras.device_bridge.remote_context import remote_command_context
from iras.device_bridge.tools import make_tools
from iras.models import PermissionLevel


class _Store:
    def __init__(self):
        self.calls = []
    def request_and_wait(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}
    def list_devices(self):
        return []


def _tool(tools, name):
    return next(item for item in tools if item.name == name)


def test_remote_chat_tool_queue_carries_session_provenance_and_actual_permission():
    store = _Store()
    tools = make_tools(store)
    with remote_command_context({"session_id": "session-abc", "requester_device": "web"}):
        _tool(tools, "device_ui_click_text").handler(text="Settings")
    call = store.calls[-1]
    assert call["remote_session_id"] == "session-abc"
    assert call["requester_device"] == "web"
    assert call["permission_level"] == int(PermissionLevel.SYSTEM_ACTION)


def test_nonremote_tool_queue_has_no_remote_session():
    store = _Store()
    tools = make_tools(store)
    _tool(tools, "device_system_info").handler()
    call = store.calls[-1]
    assert call["remote_session_id"] is None
    assert call["permission_level"] is None
