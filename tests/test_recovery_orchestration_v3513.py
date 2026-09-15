from iras.core.agent import IRASAgent
from iras.device_bridge.recovery_runtime import (
    build_recovery_handoff,
    execute_recovery_route,
)
from iras.device_bridge.task_engine import TaskTracker
from iras.models import ProviderReply, ToolCall, ToolResult


def _directive(**overrides):
    data = {
        "decision": "RETRY",
        "route": "foreground_vision",
        "tool": "device_computer_observe",
        "arguments": {"vision": "always", "scope": "foreground", "max_elements": 180},
        "purpose": "visual_semantic_regrounding_before_retry",
        "automatic": True,
        "state_changing": False,
        "requires_different_route": False,
        "reason_codes": ["verification_not_satisfied"],
    }
    data.update(overrides)
    return data


def test_handoff_exposes_fresh_grounding_without_action_replay_permission():
    handoff = build_recovery_handoff(
        _directive(),
        {
            "ok": True,
            "output": {
                "observation_id": "fresh-13",
                "foreground": {"title": "WhatsApp", "hwnd": 44},
                "vision_scope": "foreground",
                "uia_actionable": False,
                "elements": [
                    {
                        "element_id": "vision:9",
                        "label": "Search or start new chat",
                        "role": "icon",
                        "rect": {"left": 80, "top": 100, "width": 340, "height": 40},
                    }
                ],
            },
            "error": None,
        },
    )
    assert handoff["fresh_state_available"] is True
    assert handoff["fresh_observation_id"] == "fresh-13"
    assert handoff["next_step"] == "reground_target_then_plan_fresh_action"
    assert handoff["grounded_elements"][0]["element_id"] == "vision:9"
    assert handoff["action_replay_allowed"] is False
    assert handoff["state_changing_auto_recovery_allowed"] is False


def test_orchestrator_executes_only_allowlisted_read_only_observation():
    calls = []

    def execute(name, arguments):
        calls.append((name, dict(arguments)))
        return ToolResult(
            ok=True,
            output={
                "observation_id": "fresh-2",
                "foreground": {"title": "Spotify"},
                "elements": [],
            },
        )

    result = execute_recovery_route(_directive(), execute)
    assert result["executed"] is True
    assert calls == [(
        "device_computer_observe",
        {"vision": "always", "scope": "foreground", "max_elements": 180},
    )]
    assert result["handoff"]["fresh_observation_id"] == "fresh-2"
    assert result["handoff"]["action_replay_allowed"] is False


def test_orchestrator_blocks_state_changing_route_even_if_marked_automatic():
    called = False

    def execute(name, arguments):
        nonlocal called
        called = True
        raise AssertionError("must not execute")

    directive = _directive(
        route="app_refocus_reacquire",
        tool="device_app_control",
        arguments={"app": "whatsapp", "action": "focus"},
        automatic=True,
        state_changing=True,
    )
    result = execute_recovery_route(directive, execute)
    assert result["executed"] is False
    assert result["blocked_reason"] == "state_changing_auto_recovery_forbidden"
    assert called is False


def test_orchestrator_blocks_non_allowlisted_tool_even_when_claimed_read_only():
    called = False

    def execute(name, arguments):
        nonlocal called
        called = True
        raise AssertionError("must not execute")

    directive = _directive(tool="device_semantic_action", state_changing=False)
    result = execute_recovery_route(directive, execute)
    assert result["executed"] is False
    assert result["blocked_reason"] == "recovery_tool_not_read_only_allowlisted"
    assert called is False


def test_tracker_records_route_handoff_and_keeps_action_replay_disabled():
    tracker = TaskTracker("verify spotify search")
    tracker.needs_verification = True
    directive = _directive()
    payload = {"ok": True, "output": {"observation_id": "fresh-77"}, "error": None}
    handoff = build_recovery_handoff(directive, payload)
    tracker.record_automatic_recovery(directive, payload, handoff=handoff)
    snapshot = tracker.audit_summary()
    assert tracker.needs_verification is True
    assert snapshot["last_automatic_recovery_route"] == "foreground_vision"
    assert snapshot["last_automatic_recovery_next_step"] == "reground_target_then_plan_fresh_action"
    assert snapshot["automatic_action_replay_allowed"] is False


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
        return [{"type": "function", "function": {"name": n}} for n in (names or [])]
    def execute(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if name == "device_computer_verify":
            return ToolResult(
                ok=True,
                output={
                    "status": "FAIL",
                    "condition": "text_contains",
                    "scope": "foreground",
                    "vision_escalated": False,
                    "observation": {"foreground": {"title": "WhatsApp"}, "uia_actionable": False},
                    "assessment": {"evidence_sources": [], "state_delta": {"foreground_changed": False}},
                    "decision": {
                        "action": "RETRY",
                        "failure_count": 1,
                        "retry_budget_remaining": 1,
                        "goal_sufficient": False,
                        "reason_codes": ["verification_not_satisfied"],
                    },
                },
            )
        if name == "device_computer_observe":
            return ToolResult(
                ok=True,
                output={
                    "observation_id": "orchestrated-fresh-1",
                    "foreground": {"title": "WhatsApp", "hwnd": 10},
                    "vision_scope": "foreground",
                    "elements": [{"element_id": "vision:2", "label": "Darkness", "role": "text"}],
                },
            )
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
                [ToolCall(
                    "verify-1",
                    "device_computer_verify",
                    {"condition": "text_contains", "target": "Darkness", "scope": "foreground"},
                )],
                {"role": "assistant", "content": ""},
            )
        system_text = "\n".join(
            str(m.get("content") or "") for m in messages if m.get("role") == "system"
        )
        assert "AUTOMATIC OUTCOME RECOVERY ORCHESTRATION" in system_text
        assert "action_replay_allowed=False" in system_text
        assert "orchestrated-fresh-1" in system_text
        return ProviderReply(
            "Recovery state reacquired safely.",
            [],
            {"role": "assistant", "content": "Recovery state reacquired safely."},
        )


def test_agent_orchestrates_fresh_state_handoff_without_replaying_action(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tools = _Tools()
    audit = _Audit()
    agent = IRASAgent(
        provider=_Provider(),
        tools=tools,
        memory=_Memory(),
        audit=audit,
        smart_tools=True,
    )
    result = agent.handle("Verify Darkness is visible in WhatsApp.")
    assert result == "Recovery state reacquired safely."
    assert [name for name, _ in tools.calls] == [
        "device_computer_verify",
        "device_computer_observe",
    ]
    events = [payload for event, payload in audit.events if event == "automatic_outcome_recovery"]
    assert events
    assert events[0]["handoff"]["fresh_observation_id"] == "orchestrated-fresh-1"
    assert events[0]["action_replay_allowed"] is False
