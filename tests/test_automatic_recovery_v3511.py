from iras.core.agent import IRASAgent
from iras.device_bridge.recovery_runtime import build_recovery_directive
from iras.device_bridge.task_engine import TaskTracker
from iras.models import ProviderReply, ToolCall, ToolResult


def _verification_output(action: str):
    return {
        "status": "FAIL" if action != "ACCEPT" else "PASS",
        "scope": "foreground",
        "decision": {
            "action": action,
            "goal_sufficient": action == "ACCEPT",
            "failure_count": 1,
            "retry_budget_remaining": 1,
            "reason_codes": ["test_reason"],
        },
    }


def test_retry_builds_read_only_fresh_observation():
    directive = build_recovery_directive(
        _verification_output("RETRY"),
        {"scope": "foreground"},
    )
    assert directive is not None
    assert directive["tool"] == "device_computer_observe"
    assert directive["arguments"] == {
        "vision": "auto",
        "scope": "foreground",
        "max_elements": 180,
    }
    assert directive["state_changing"] is False


def test_recover_forces_visual_reacquisition_and_different_route():
    directive = build_recovery_directive(
        _verification_output("RECOVER"),
        {"scope": "foreground"},
    )
    assert directive is not None
    assert directive["arguments"]["vision"] == "always"
    assert directive["requires_different_route"] is True


def test_accept_does_not_schedule_automatic_recovery():
    assert build_recovery_directive(_verification_output("ACCEPT"), {}) is None


def test_tracker_records_recovery_without_clearing_pending_verification():
    tracker = TaskTracker("search and verify")
    tracker.needs_verification = True
    directive = build_recovery_directive(_verification_output("RETRY"), {})
    tracker.record_automatic_recovery(
        directive,
        {
            "ok": True,
            "output": {"observation_id": "fresh-1"},
            "error": None,
        },
    )
    assert tracker.needs_verification is True
    assert tracker.automatic_recovery_steps == 1
    assert tracker.last_automatic_recovery_decision == "RETRY"
    assert tracker.last_automatic_recovery_observation_id == "fresh-1"


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
        self.verify_calls = 0
        self.observe_calls = []

    def schemas(self, names=None):
        return [{"type": "function", "function": {"name": n}} for n in (names or [])]

    def execute(self, name, arguments):
        if name == "device_computer_observe":
            self.observe_calls.append(dict(arguments))
            return ToolResult(
                ok=True,
                output={
                    "observation_id": "auto-recovery-observation",
                    "foreground": {"title": "WhatsApp"},
                    "elements": [{"element_id": "uia:1", "label": "Darkness"}],
                    "element_count": 1,
                    "vision_scope": None,
                },
            )
        if name == "device_computer_verify":
            self.verify_calls += 1
            if self.verify_calls == 1:
                return ToolResult(
                    ok=True,
                    output={
                        "status": "FAIL",
                        "scope": "foreground",
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
                    "scope": "foreground",
                    "decision": {
                        "action": "ACCEPT",
                        "failure_count": 0,
                        "retry_budget_remaining": 2,
                        "goal_sufficient": True,
                        "reason_codes": ["verification_condition_accepted"],
                    },
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
                    {
                        "condition": "text_contains",
                        "target": "hello",
                        "scope": "foreground",
                    },
                )],
                {"role": "assistant", "content": ""},
            )
        if self.calls == 2:
            assert any(
                m.get("role") == "system"
                and "AUTOMATIC OUTCOME RECOVERY" in str(m.get("content") or "")
                for m in messages
            )
            return ProviderReply(
                "",
                [ToolCall(
                    "verify-2",
                    "device_computer_verify",
                    {
                        "condition": "text_contains",
                        "target": "hello",
                        "scope": "foreground",
                    },
                )],
                {"role": "assistant", "content": ""},
            )
        return ProviderReply(
            "Verified after automatic recovery.",
            [],
            {"role": "assistant", "content": "Verified after automatic recovery."},
        )


def test_agent_executes_read_only_recovery_before_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tools = _Tools()
    audit = _Audit()
    provider = _Provider()
    agent = IRASAgent(
        provider=provider,
        tools=tools,
        memory=_Memory(),
        audit=audit,
        smart_tools=True,
    )

    result = agent.handle("Message Darkness on whatsapp saying hello.")

    assert result == "Verified after automatic recovery."
    # v3.5.12 route selection sees a semantic verification failure with no
    # actionable UIA evidence in the verification payload, so it chooses a
    # stronger foreground-vision reacquisition rather than a generic auto read.
    assert tools.observe_calls == [{
        "vision": "always",
        "scope": "foreground",
        "max_elements": 180,
    }]
    assert any(event == "automatic_outcome_recovery" for event, _ in audit.events)
