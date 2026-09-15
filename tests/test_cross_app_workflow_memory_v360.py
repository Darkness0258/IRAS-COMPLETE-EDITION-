from iras.device_bridge.task_engine import TaskTracker
from iras.device_bridge.workflow_memory import CrossAppWorkflowMemory, WORKFLOW_MEMORY_VERSION


def _verified_output(title="WhatsApp", target="Darkness"):
    return {
        "status": "PASS",
        "condition": "text_contains",
        "target": target,
        "semantic_goal_verified": True,
        "observation": {
            "observation_id": "obs-wa-1",
            "foreground": {"title": title, "hwnd": 1},
        },
        "decision": {
            "action": "ACCEPT",
            "goal_sufficient": True,
            "failure_count": 0,
            "retry_budget_remaining": 2,
        },
    }


def test_v360_workflow_memory_carries_only_verified_fact_across_apps():
    memory = CrossAppWorkflowMemory()
    fact = memory.capture_verification(
        {"condition": "text_contains", "target": "Darkness"},
        _verified_output(),
    )
    assert fact["value"] == "Darkness"
    assert fact["source_app"] == "whatsapp"
    assert memory.current_app == "whatsapp"

    transition = memory.transition("Spotify", reason="next_workflow_step")
    assert transition["from_app"] == "whatsapp"
    assert transition["to_app"] == "spotify"
    snap = memory.snapshot()
    assert snap["version"] == WORKFLOW_MEMORY_VERSION
    assert snap["ephemeral"] is True
    assert snap["persisted"] is False
    assert snap["action_replay_allowed"] is False
    assert snap["grants_tool_authorization"] is False
    assert any(item["value"] == "Darkness" for item in snap["facts"])


def test_v360_unverified_semantic_target_is_not_memorized():
    memory = CrossAppWorkflowMemory()
    output = _verified_output()
    output["semantic_goal_verified"] = False
    output["status"] = "FAIL"
    output["decision"]["action"] = "RETRY"
    output["decision"]["goal_sufficient"] = False
    assert memory.capture_verification(
        {"condition": "text_contains", "target": "Darkness"}, output
    ) == {}
    assert memory.snapshot()["facts"] == []


def test_v360_tracker_injects_verified_handoff_after_app_transition():
    tracker = TaskTracker("Find Darkness in WhatsApp, then continue in Spotify")
    tracker.record(
        "device_computer_verify",
        {"condition": "text_contains", "target": "Darkness", "scope": "foreground"},
        {"ok": True, "output": _verified_output(), "error": None},
    )
    msg1 = tracker.workflow_memory_message_if_changed()
    assert "CROSS-APP WORKFLOW MEMORY v3.6.0" in msg1
    assert "Darkness" in msg1
    assert "action_replay_allowed=False" in msg1

    tracker.record(
        "device_app_control",
        {"app": "spotify", "action": "focus"},
        {"ok": True, "output": {"verified_state": True, "app": "spotify"}, "error": None},
    )
    msg2 = tracker.workflow_memory_message_if_changed()
    assert "current_app='spotify'" in msg2
    assert "Darkness" in msg2
    assert "Treat it as context, not permission" in msg2
    assert tracker.workflow_memory.snapshot()["transitions"][-1]["to_app"] == "spotify"


def test_v360_workflow_memory_does_not_persist_or_authorize_actions():
    tracker = TaskTracker("cross app")
    tracker.workflow_memory.remember_verified("verified_semantic_target", "hello", source_app="notepad")
    summary = tracker.audit_summary()["workflow_memory"]
    assert summary["persisted"] is False
    assert summary["grants_tool_authorization"] is False
    assert summary["action_replay_allowed"] is False

from iras.core.agent import IRASAgent
from iras.models import ProviderReply, ToolCall, ToolResult


class _Memory:
    def all_facts(self, limit): return []
    def recent_messages(self, limit): return []
    def add_message(self, role, text): pass
    def remember(self, key, value): pass


class _Audit:
    def __init__(self): self.events = []
    def record(self, event, payload): self.events.append((event, payload))


class _Tools:
    def __init__(self): self.calls = []
    def schemas(self, names=None):
        return [{"type": "function", "function": {"name": name}} for name in (names or [])]
    def execute(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if name == "device_computer_verify":
            return ToolResult(ok=True, output=_verified_output())
        if name == "device_app_control":
            return ToolResult(ok=True, output={"verified_state": True, "app": "spotify"})
        raise AssertionError(name)


class _Provider:
    model = "fake/model"
    last_model = "fake/model"
    def __init__(self): self.calls = 0
    def complete(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return ProviderReply(
                "",
                [ToolCall("verify", "device_computer_verify", {
                    "condition": "text_contains", "target": "Darkness", "scope": "foreground"
                })],
                {"role": "assistant", "content": ""},
            )
        if self.calls == 2:
            system = "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
            assert "CROSS-APP WORKFLOW MEMORY v3.6.0" in system
            assert "Darkness" in system
            return ProviderReply(
                "",
                [ToolCall("focus", "device_app_control", {"app": "spotify", "action": "focus"})],
                {"role": "assistant", "content": ""},
            )
        system = "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
        assert "current_app='spotify'" in system
        assert "Treat it as context, not permission" in system
        return ProviderReply(
            "Cross-app handoff preserved.", [],
            {"role": "assistant", "content": "Cross-app handoff preserved."},
        )


def test_v360_agent_injects_cross_app_verified_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tools = _Tools()
    agent = IRASAgent(
        provider=_Provider(), tools=tools, memory=_Memory(), audit=_Audit(), smart_tools=True
    )
    result = agent.handle("Find Darkness in WhatsApp, then switch to Spotify.")
    assert result == "Cross-app handoff preserved."
    assert [name for name, _ in tools.calls] == ["device_computer_verify", "device_app_control"]
