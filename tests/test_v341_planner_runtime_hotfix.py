from iras.core.agent import IRASAgent
from iras.device_bridge.planner import SAFE_DEVICE_PLANNER_TOOLS
from iras.device_bridge.task_engine import TaskTracker
from iras.models import ProviderReply, ToolCall, ToolResult


def test_compound_spotify_settings_enters_full_planner():
    selected = IRASAgent._device_tool_names(
        "Open Spotify and open Settings."
    )
    assert selected == set(SAFE_DEVICE_PLANNER_TOOLS)
    assert "device_observe_ui" in selected
    assert "device_semantic_action" in selected
    assert "device_skill_find" in selected


def test_whatsapp_message_enters_full_planner():
    selected = IRASAgent._device_tool_names(
        "Message Darkness on whatsapp saying hello."
    )
    assert selected == set(SAFE_DEVICE_PLANNER_TOOLS)


def test_simple_spotify_open_keeps_fast_path():
    selected = IRASAgent._device_tool_names("Open Spotify")
    assert selected == {"device_open_app"}


def test_tasktracker_empty_final_is_evidence_aware(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path/"skills.json"))
    tracker = TaskTracker("test")
    tracker.successful_calls = 1
    tracker.needs_verification = False
    text = tracker.empty_final_response().lower()
    assert "verified step-level progress" in text
    assert "goal-level evidence" in text
    assert "completed verified tool steps" not in text
    assert "lost that response" not in text


class _Memory:
    def all_facts(self, limit): return []
    def recent_messages(self, limit): return []
    def add_message(self, role, text): pass
    def remember(self, key, value): pass


class _Audit:
    def record(self, event, payload): pass


class _Tools:
    def schemas(self, names=None):
        return [{"type":"function","function":{"name":n}} for n in (names or [])]

    def execute(self, name, arguments):
        assert name == "device_semantic_action"
        return ToolResult(
            ok=True,
            output={
                "selected_element": {
                    "name": "Darkness",
                    "automation_id": "contact-darkness",
                    "role": "ListItem",
                },
                "verification_observation": {
                    "window_name": "WhatsApp",
                    "element_count": 1,
                    "elements": [{"name":"Darkness"}],
                },
            },
        )


class _Provider:
    model = "fake/model"
    last_model = "fake/model"

    def __init__(self): self.calls = 0

    def complete(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return ProviderReply(
                "",
                [ToolCall(
                    "1",
                    "device_semantic_action",
                    {
                        "app":"WhatsApp",
                        "action":"click",
                        "target":"Darkness",
                    },
                )],
                {"role":"assistant","content":""},
            )
        if self.calls == 2:
            return ProviderReply("", [], {"role":"assistant","content":""})
        return ProviderReply(
            "Message workflow finished with verified UI evidence.",
            [],
            {
                "role":"assistant",
                "content":"Message workflow finished with verified UI evidence.",
            },
        )


def test_empty_post_tool_reply_is_retried_once(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path/"skills.json"))
    provider = _Provider()
    agent = IRASAgent(
        provider=provider,
        tools=_Tools(),
        memory=_Memory(),
        audit=_Audit(),
        smart_tools=True,
    )
    result = agent.handle("Message Darkness on whatsapp saying hello.")
    assert provider.calls == 3
    assert result == "Message workflow finished with verified UI evidence."
    assert "lost that response" not in result.lower()


def test_specialized_project_route_remains_narrow():
    selected = IRASAgent._device_tool_names(
        "open my project in VS Code on my PC"
    )
    assert selected == {"device_open_project"}


def test_specialized_run_tests_route_remains_narrow():
    selected = IRASAgent._device_tool_names(
        "run the tests in my project on my PC"
    )
    assert selected == {"device_run_tests"}
