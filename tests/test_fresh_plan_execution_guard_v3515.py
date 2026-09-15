from iras.device_bridge.fresh_action_execution import (
    build_chained_verification_call,
    validate_fresh_plan_execution,
)
from iras.device_bridge.fresh_action_planning import build_fresh_action_plan
from iras.device_bridge.task_engine import TaskTracker


def _handoff():
    return {
        "decision": "RETRY",
        "route": "foreground_vision",
        "recovery_ok": True,
        "fresh_state_available": True,
        "fresh_observation_id": "fresh-3515",
        "foreground": {"title": "WhatsApp", "hwnd": 10},
        "vision_scope": "foreground",
        "uia_actionable": False,
        "grounded_elements": [
            {
                "element_id": "vision:7",
                "label": "Darkness",
                "role": "text",
                "rect": {"left": 150, "top": 260, "width": 86, "height": 19},
            }
        ],
        "requires_different_route": False,
        "action_replay_allowed": False,
        "verification_context": {
            "condition": "text_contains",
            "target": "Darkness",
            "scope": "foreground",
        },
    }


def _plan():
    return build_fresh_action_plan(_handoff())


def test_v3515_guard_accepts_only_fresh_bound_action():
    ok, reason = validate_fresh_plan_execution(
        _plan(),
        "device_computer_action",
        {
            "observation_id": "fresh-3515",
            "action": "click",
            "element_id": "vision:7",
        },
    )
    assert ok is True
    assert reason == ""


def test_v3515_guard_rejects_stale_binding_and_nonready_plan():
    ok, reason = validate_fresh_plan_execution(
        _plan(),
        "device_computer_action",
        {
            "observation_id": "old-observation",
            "action": "click",
            "element_id": "vision:7",
        },
    )
    assert ok is False
    assert reason == "stale_observation_id_after_recovery"

    blocked = dict(_plan())
    blocked["status"] = "AMBIGUOUS_TARGET"
    ok, reason = validate_fresh_plan_execution(
        blocked,
        "device_computer_action",
        {
            "observation_id": "fresh-3515",
            "action": "click",
            "element_id": "vision:7",
        },
    )
    assert ok is False
    assert reason == "fresh_action_plan_not_ready_for_execution"


def test_v3515_builds_read_only_verification_chain_from_fresh_baseline():
    call = build_chained_verification_call(_plan())
    assert call == {
        "tool": "device_computer_verify",
        "arguments": {
            "condition": "text_contains",
            "target": "Darkness",
            "prior_observation_id": "fresh-3515",
            "vision": "auto",
            "scope": "foreground",
        },
        "automatic": True,
        "state_changing": False,
        "purpose": "verify_fresh_planned_action_semantic_outcome",
        "action_replay_allowed": False,
    }


def test_v3515_tracker_arms_verification_only_after_valid_fresh_action():
    tracker = TaskTracker("open Darkness")
    plan = _plan()
    tracker.record_automatic_recovery(
        {"decision": "RETRY", "route": "foreground_vision"},
        {"ok": True, "output": {"observation_id": "fresh-3515"}},
        handoff=_handoff(),
        fresh_plan=plan,
    )
    allowed, reason = tracker.before_call(
        "device_computer_action",
        {
            "observation_id": "fresh-3515",
            "action": "click",
            "element_id": "vision:7",
        },
    )
    assert allowed is True
    assert reason == ""
    tracker.record(
        "device_computer_action",
        {
            "observation_id": "fresh-3515",
            "action": "click",
            "element_id": "vision:7",
        },
        {"ok": True, "output": {"action_verified": True}},
    )
    assert tracker.chained_verification_pending is True
    assert tracker.chained_verification_call["tool"] == "device_computer_verify"
    assert tracker.chained_verification_call["arguments"]["prior_observation_id"] == "fresh-3515"
    assert tracker.recovery_fresh_plan_pending is False


def test_v3515_tracker_does_not_arm_chain_for_ordinary_action():
    tracker = TaskTracker("click button")
    tracker.record(
        "device_computer_action",
        {"observation_id": "ordinary", "action": "click", "element_id": "uia:1"},
        {"ok": True, "output": {"action_verified": True}},
    )
    assert tracker.chained_verification_pending is False
    assert tracker.chained_verification_call == {}


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
    def __init__(self):
        self.calls = []
        self.verify_count = 0

    def schemas(self, names=None):
        return [{"type": "function", "function": {"name": n}} for n in (names or [])]

    def execute(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if name == "device_computer_verify":
            self.verify_count += 1
            if self.verify_count == 1:
                return ToolResult(
                    ok=True,
                    output={
                        "status": "FAIL",
                        "condition": "text_contains",
                        "target": "Darkness",
                        "scope": "foreground",
                        "observation": {
                            "foreground": {"title": "WhatsApp", "hwnd": 42},
                            "uia_actionable": False,
                        },
                        "assessment": {
                            "evidence_sources": [],
                            "state_delta": {"foreground_changed": False},
                        },
                        "decision": {
                            "action": "RETRY",
                            "failure_count": 1,
                            "retry_budget_remaining": 1,
                            "goal_sufficient": False,
                            "reason_codes": ["verification_not_satisfied"],
                        },
                    },
                )
            return ToolResult(
                ok=True,
                output={
                    "status": "PASS",
                    "condition": "text_contains",
                    "target": "Darkness",
                    "scope": "foreground",
                    "confidence": 0.98,
                    "semantic_goal_verified": True,
                    "decision": {
                        "action": "ACCEPT",
                        "failure_count": 0,
                        "retry_budget_remaining": 2,
                        "goal_sufficient": True,
                        "reason_codes": ["verification_condition_accepted"],
                    },
                },
            )
        if name == "device_computer_observe":
            return ToolResult(
                ok=True,
                output={
                    "observation_id": "fresh-agent-3515",
                    "foreground": {"title": "WhatsApp", "hwnd": 42},
                    "vision_scope": "foreground",
                    "uia_actionable": False,
                    "elements": [
                        {"element_id": "vision:7", "label": "Darkness", "role": "text"},
                    ],
                },
            )
        if name == "device_computer_action":
            return ToolResult(
                ok=True,
                output={
                    "action": "click",
                    "action_verified": True,
                    "closed_loop_observed": True,
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
                    "verify-3515",
                    "device_computer_verify",
                    {"condition": "text_contains", "target": "Darkness", "scope": "foreground"},
                )],
                {"role": "assistant", "content": ""},
            )
        if self.calls == 2:
            system_text = "\n".join(
                str(message.get("content") or "")
                for message in messages
                if message.get("role") == "system"
            )
            assert "fresh-agent-3515" in system_text
            assert "vision:7" in system_text
            return ProviderReply(
                "",
                [ToolCall(
                    "fresh-action-3515",
                    "device_computer_action",
                    {
                        "observation_id": "fresh-agent-3515",
                        "action": "click",
                        "element_id": "vision:7",
                    },
                )],
                {"role": "assistant", "content": ""},
            )

        system_text = "\n".join(
            str(message.get("content") or "")
            for message in messages
            if message.get("role") == "system"
        )
        assert "FRESH-ACTION AUTOMATIC VERIFICATION v3.5.15" in system_text
        assert "semantic_goal_verified=True" in system_text
        assert "action_replay_allowed" not in system_text or "not replayed" in system_text
        return ProviderReply(
            "Fresh action verified.",
            [],
            {"role": "assistant", "content": "Fresh action verified."},
        )


def test_v3515_agent_chains_verification_after_fresh_action(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    audit = _Audit()
    tools = _Tools()
    agent = IRASAgent(
        provider=_Provider(),
        tools=tools,
        memory=_Memory(),
        audit=audit,
        smart_tools=True,
    )
    result = agent.handle("Verify Darkness is visible in WhatsApp.")
    assert result == "Fresh action verified."
    assert [name for name, _ in tools.calls] == [
        "device_computer_verify",
        "device_computer_observe",
        "device_computer_action",
        "device_computer_verify",
    ]
    auto_events = [payload for event, payload in audit.events if event == "fresh_action_automatic_verification"]
    assert auto_events
    assert auto_events[0]["verification_call"]["state_changing"] is False
    assert auto_events[0]["action_replay_allowed"] is False
    assert auto_events[0]["verification_payload"]["output"]["semantic_goal_verified"] is True
