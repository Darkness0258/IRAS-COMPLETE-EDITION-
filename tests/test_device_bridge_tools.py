from iras.device_bridge.tools import make_tools


class FakeStore:
    def __init__(self):
        self.calls = []

    def list_devices(self):
        return [{"device_id": "pc", "online": True}]

    def request_and_wait(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, "action": kwargs["action"]}


def test_device_tools_use_bounded_actions():
    store = FakeStore()
    tools = {item.name: item for item in make_tools(store)}

    result = tools["device_open_app"].handler(app="vscode")
    assert result["action"] == "open_app"
    assert store.calls[-1]["arguments"] == {"app": "vscode"}


def test_no_generic_remote_shell_tool():
    names = {item.name for item in make_tools(FakeStore())}
    assert "device_shell" not in names
    assert "remote_shell" not in names
