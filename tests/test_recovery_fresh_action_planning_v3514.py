from iras.device_bridge.fresh_action_planning import (
    build_fresh_action_plan,
    fresh_action_plan_message,
    validate_fresh_action_call,
)
from iras.device_bridge.recovery_runtime import build_recovery_directive, build_recovery_handoff
from iras.device_bridge.task_engine import TaskTracker


def _handoff(elements=None, **overrides):
    data = {
        "decision": "RETRY",
        "route": "foreground_vision",
        "recovery_ok": True,
        "fresh_state_available": True,
        "fresh_observation_id": "fresh-3514",
        "foreground": {"title": "WhatsApp", "hwnd": 10},
        "vision_scope": "foreground",
        "uia_actionable": False,
        "grounded_elements": elements or [
            {
                "element_id": "vision:4",
                "label": "Darkness",
                "role": "text",
                "rect": {"left": 10, "top": 20, "width": 80, "height": 20},
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
    data.update(overrides)
    return data


def test_fresh_plan_regrounds_target_from_recovery_observation():
    plan = build_fresh_action_plan(_handoff())
    assert plan["status"] == "READY_FOR_FRESH_ACTION_SELECTION"
    assert plan["fresh_observation_id"] == "fresh-3514"
    assert plan["selected_element"]["element_id"] == "vision:4"
    assert plan["action_replay_allowed"] is False
    assert plan["requires_new_action_choice"] is True
    assert plan["requires_post_action_verification"] is True


def test_fresh_plan_marks_duplicate_exact_matches_ambiguous():
    plan = build_fresh_action_plan(_handoff(elements=[
        {"element_id": "vision:1", "label": "Darkness", "role": "text"},
        {"element_id": "vision:2", "label": "Darkness", "role": "text"},
    ]))
    assert plan["status"] == "AMBIGUOUS_TARGET"
    assert plan["selected_element"] is None
    assert len(plan["candidate_elements"]) == 2


def test_fresh_plan_blocks_when_recovery_state_is_missing():
    plan = build_fresh_action_plan(_handoff(
        recovery_ok=False,
        fresh_state_available=False,
        fresh_observation_id=None,
    ))
    assert plan["status"] == "BLOCKED"
    assert plan["selected_element"] is None


def test_validate_fresh_action_rejects_stale_observation_and_element_ids():
    plan = build_fresh_action_plan(_handoff())
    ok, reason = validate_fresh_action_call(
        plan,
        "device_computer_action",
        {"observation_id": "old-observation", "action": "click", "element_id": "vision:4"},
    )
    assert ok is False
    assert reason == "stale_observation_id_after_recovery"

    ok, reason = validate_fresh_action_call(
        plan,
        "device_computer_action",
        {"observation_id": "fresh-3514", "action": "click", "element_id": "vision:999"},
    )
    assert ok is False
    assert reason == "stale_or_unobserved_element_id_after_recovery"


def test_validate_fresh_action_accepts_only_fresh_binding():
    plan = build_fresh_action_plan(_handoff())
    assert validate_fresh_action_call(
        plan,
        "device_computer_action",
        {"observation_id": "fresh-3514", "action": "click", "element_id": "vision:4"},
    ) == (True, "")


def test_tracker_blocks_stale_post_recovery_computer_action():
    tracker = TaskTracker("open Darkness")
    directive = {
        "decision": "RETRY",
        "route": "foreground_vision",
    }
    handoff = _handoff()
    tracker.record_automatic_recovery(
        directive,
        {"ok": True, "output": {"observation_id": "fresh-3514"}},
        handoff=handoff,
    )
    assert tracker.recovery_fresh_plan_pending is True

    allowed, reason = tracker.before_call(
        "device_computer_action",
        {"observation_id": "stale", "action": "click", "element_id": "vision:4"},
    )
    assert allowed is False
    assert "stale" in reason.lower()

    allowed, reason = tracker.before_call(
        "device_computer_action",
        {"observation_id": "fresh-3514", "action": "click", "element_id": "vision:999"},
    )
    assert allowed is False
    assert "element_id" in reason

    allowed, reason = tracker.before_call(
        "device_computer_action",
        {"observation_id": "fresh-3514", "action": "click", "element_id": "vision:4"},
    )
    assert allowed is True
    assert reason == ""


def test_recovery_directive_preserves_verification_context_for_fresh_planning():
    output = {
        "status": "FAIL",
        "condition": "text_contains",
        "scope": "foreground",
        "observation": {"uia_actionable": False},
        "assessment": {"evidence_sources": []},
        "decision": {
            "action": "RETRY",
            "reason_codes": ["verification_not_satisfied"],
        },
    }
    directive = build_recovery_directive(
        output,
        {
            "condition": "text_contains",
            "target": "Darkness",
            "scope": "foreground",
            "prior_observation_id": "before-1",
        },
    )
    assert directive["verification_context"] == {
        "condition": "text_contains",
        "target": "Darkness",
        "scope": "foreground",
        "prior_observation_id": "before-1",
    }
    handoff = build_recovery_handoff(
        directive,
        {
            "ok": True,
            "output": {
                "observation_id": "fresh-3514",
                "elements": [{"element_id": "vision:4", "label": "Darkness", "role": "text"}],
            },
        },
    )
    plan = build_fresh_action_plan(handoff)
    assert plan["selected_element"]["element_id"] == "vision:4"
    assert "do not replay" in fresh_action_plan_message(plan).lower()

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
                    "observation_id": "fresh-agent-3514",
                    "foreground": {"title": "WhatsApp", "hwnd": 42},
                    "vision_scope": "foreground",
                    "uia_actionable": False,
                    "elements": [
                        {"element_id": "vision:4", "label": "Darkness", "role": "text"},
                    ],
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
                    "verify-3514",
                    "device_computer_verify",
                    {"condition": "text_contains", "target": "Darkness", "scope": "foreground"},
                )],
                {"role": "assistant", "content": ""},
            )
        system_text = "\n".join(
            str(message.get("content") or "")
            for message in messages
            if message.get("role") == "system"
        )
        assert "RECOVERY-AWARE FRESH ACTION PLAN v3.5.14" in system_text
        assert "fresh-agent-3514" in system_text
        assert "vision:4" in system_text
        assert "do not replay" in system_text.lower()
        return ProviderReply(
            "Fresh recovery plan received.",
            [],
            {"role": "assistant", "content": "Fresh recovery plan received."},
        )


def test_agent_receives_recovery_aware_fresh_action_plan(tmp_path, monkeypatch):
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
    assert result == "Fresh recovery plan received."
    assert [name for name, _ in tools.calls] == [
        "device_computer_verify",
        "device_computer_observe",
    ]
    plan_events = [payload for event, payload in audit.events if event == "recovery_aware_fresh_action_plan"]
    assert plan_events
    assert plan_events[0]["selected_element"]["element_id"] == "vision:4"
    assert plan_events[0]["action_replay_allowed"] is False
