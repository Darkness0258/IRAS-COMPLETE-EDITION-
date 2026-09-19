from iras.core.agent import IRASAgent
from iras.device_bridge.tools import make_tools
from iras.models import ProviderReply, ToolCall, ToolResult


class _Store:
    def __init__(self):
        self.calls = []
        self.files = {}

    def list_devices(self):
        return []

    def request_and_wait(self, **kwargs):
        action = kwargs["action"]
        args = dict(kwargs.get("arguments") or {})
        self.calls.append((action, args))
        if action == "system_info":
            return {"user": "mhamz", "allowed_roots": [r"C:\\", r"D:\\"]}
        if action == "make_directory":
            return {"path": args["path"], "created": True}
        if action == "write_text":
            self.files[args["path"]] = args["content"]
            return {"path": args["path"], "bytes": len(args["content"].encode("utf-8"))}
        if action == "read_text":
            return {"path": args["path"], "content": self.files[args["path"]]}
        if action == "open_project":
            return {"opened": args["path"], "app": "vscode"}
        if action == "interact_app":
            return {"app": "code", "actions_completed": [x["action"] for x in args["actions"]]}
        if action == "observe_ui":
            return {"app": "code", "elements": [{"name": "*****", "role": "Text"}]}
        raise AssertionError(action)


def test_quick_code_router_avoids_gui_typing_for_simple_vscode_tasks():
    assert IRASAgent._device_tool_names(
        "open vs code and write a python hello world code"
    ) == {"device_quick_code"}
    assert IRASAgent._device_tool_names(
        "now open a python triangle code"
    ) == {"device_quick_code"}
    assert IRASAgent._device_tool_names(
        "open my project in VS Code on my PC"
    ) == {"device_open_project"}


def test_quick_code_composes_existing_bridge_actions_and_verifies_readback():
    store = _Store()
    tool = {item.name: item for item in make_tools(store)}["device_quick_code"]
    out = tool.handler(
        content='print("hello")\n',
        filename="hello.py",
        language="python",
        open_in_vscode=True,
    )
    assert out["created"] is True
    assert out["verified"] is True
    assert out["path"] == r"D:\Projects\IRAS-QuickCode\hello.py"
    assert out["vscode_opened"] is True
    assert out["file_focused"] is True
    assert [name for name, _ in store.calls] == [
        "system_info",
        "make_directory",
        "write_text",
        "read_text",
        "open_project",
        "interact_app",
    ]


class _Memory:
    def all_facts(self, limit): return []
    def recent_messages(self, limit): return []
    def add_message(self, role, text): pass
    def remember(self, key, value): pass


class _Audit:
    def record(self, event, payload): pass


class _Tools:
    def __init__(self): self.calls = []
    def schemas(self, names=None):
        return [{"type":"function","function":{"name":n}} for n in (names or [])]
    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        assert name == "device_quick_code"
        return ToolResult(True, output={
            "created": True,
            "verified": True,
            "path": r"D:\Projects\IRAS-QuickCode\triangle.py",
            "vscode_opened": True,
        })


class _Provider:
    model = "fake/model"
    last_model = "fake/model"
    def __init__(self): self.calls = 0
    def complete(self, messages, tools):
        self.calls += 1
        if self.calls > 1:
            raise AssertionError("Quick Code should terminate after the verified tool result.")
        return ProviderReply(
            "",
            [ToolCall("quick-1", "device_quick_code", {
                "content": "for i in range(1, 5):\n    print('*' * i)\n",
                "filename": "triangle.py",
                "language": "python",
            })],
            {"role": "assistant", "content": ""},
        )


def test_quick_code_success_short_circuits_model_loop():
    provider = _Provider()
    tools = _Tools()
    agent = IRASAgent(provider, tools, _Memory(), _Audit(), smart_tools=True)
    result = agent.handle("open vs code and write a python triangle program")
    assert provider.calls == 1
    assert tools.calls and tools.calls[0][0] == "device_quick_code"
    assert "created and verified" in result.lower()
    assert "triangle.py" in result
    assert "opened it in vs code" in result.lower()


def test_quick_code_run_in_vscode_uses_integrated_terminal_and_sample_input():
    store = _Store()
    path = r"D:\Projects\IRAS-QuickCode\triangle.py"
    store.files[path] = (
        "def triangle(n):\n"
        "    for i in range(1, n + 1):\n"
        "        print('*' * i)\n"
        "rows = int(input('Enter number of rows: '))\n"
        "triangle(rows)\n"
    )
    tool = {item.name: item for item in make_tools(store)}["device_quick_code_run_in_vscode"]
    out = tool.handler(path=path, language="python", sample_input="5")
    assert out["executed"] is True
    assert out["filename"] == "triangle.py"
    assert out["command"] == 'python "triangle.py"'
    assert out["input_sent"] is True
    interactions = [args for name, args in store.calls if name == "interact_app"]
    assert len(interactions) == 2
    run_actions = interactions[-1]["actions"]
    assert any(a.get("text") == "Terminal: Create New Terminal" for a in run_actions)
    assert any(a.get("text") == 'python "triangle.py"' for a in run_actions)
    assert any(a.get("text") == "5" for a in run_actions)
    assert store.calls[-1][0] == "observe_ui"


class _FollowupTools(_Tools):
    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "device_quick_code":
            return ToolResult(True, output={
                "created": True,
                "verified": True,
                "path": r"D:\Projects\IRAS-QuickCode\triangle.py",
                "workspace": r"D:\Projects\IRAS-QuickCode",
                "filename": "triangle.py",
                "language": "python",
                "vscode_opened": True,
            })
        if name == "device_quick_code_run_in_vscode":
            return ToolResult(True, output={
                "executed": True,
                "path": arguments["path"],
                "filename": "triangle.py",
                "language": "python",
                "input_sent": True,
            })
        raise AssertionError(name)


def test_quick_code_followup_try_this_in_vscode_bypasses_model():
    provider = _Provider()
    tools = _FollowupTools()
    agent = IRASAgent(provider, tools, _Memory(), _Audit(), smart_tools=True)
    first = agent.handle("open vs code and write a python triangle program")
    assert "triangle.py" in first
    assert provider.calls == 1

    second = agent.handle("try this in vs code")
    assert provider.calls == 1
    assert tools.calls[-1][0] == "device_quick_code_run_in_vscode"
    assert tools.calls[-1][1]["path"] == r"D:\Projects\IRAS-QuickCode\triangle.py"
    assert "ran triangle.py in vs code's integrated terminal" in second.lower()
