from iras.device_bridge.recovery_runtime import (
    build_recovery_directive,
    select_recovery_route,
)


def _output(
    action: str,
    *,
    condition: str = "text_contains",
    uia_actionable: bool = True,
    vision_escalated: bool = False,
    evidence_sources=None,
    foreground_changed: bool = False,
    prior_title: str = "WhatsApp",
):
    return {
        "status": "FAIL",
        "condition": condition,
        "scope": "foreground",
        "vision_escalated": vision_escalated,
        "prior_foreground": {"title": prior_title, "hwnd": 10},
        "observation": {
            "foreground": {"title": "WhatsApp", "hwnd": 10},
            "uia_actionable": uia_actionable,
        },
        "assessment": {
            "evidence_sources": list(evidence_sources or []),
            "state_delta": {"foreground_changed": foreground_changed},
        },
        "decision": {
            "action": action,
            "goal_sufficient": False,
            "failure_count": 1,
            "retry_budget_remaining": 1,
            "reason_codes": ["verification_not_satisfied"],
        },
    }


def test_retry_prefers_uia_reground_when_foreground_is_stable():
    route = select_recovery_route(_output("RETRY"), {"scope": "foreground"})
    assert route is not None
    assert route["route"] == "uia_reground"
    assert route["automatic"] is True
    assert route["arguments"] == {
        "vision": "off",
        "scope": "foreground",
        "max_elements": 180,
    }


def test_retry_uses_foreground_vision_when_uia_is_not_actionable():
    route = select_recovery_route(
        _output("RETRY", uia_actionable=False),
        {"scope": "foreground"},
    )
    assert route is not None
    assert route["route"] == "foreground_vision"
    assert route["arguments"]["vision"] == "always"
    assert route["arguments"]["scope"] == "foreground"


def test_escalate_vision_forces_visual_semantic_regrounding():
    output = _output("ESCALATE_VISION")
    output["decision"]["reason_codes"] = [
        "semantic_target_needs_visual_confirmation"
    ]
    route = select_recovery_route(output, {"scope": "foreground"})
    assert route is not None
    assert route["route"] == "foreground_vision"
    assert route["automatic"] is True


def test_foreground_drift_selects_conservative_app_refocus_without_auto_execution():
    route = select_recovery_route(
        _output("RETRY", foreground_changed=True, prior_title="WhatsApp"),
        {"scope": "foreground"},
    )
    assert route is not None
    assert route["route"] == "app_refocus_reacquire"
    assert route["tool"] == "device_app_control"
    assert route["arguments"] == {"app": "whatsapp", "action": "focus"}
    assert route["automatic"] is False
    assert route["state_changing"] is True


def test_unknown_foreground_drift_uses_read_only_desktop_vision():
    route = select_recovery_route(
        _output("RETRY", foreground_changed=True, prior_title="Unknown App 937"),
        {"scope": "foreground"},
    )
    assert route is not None
    assert route["route"] == "desktop_vision"
    assert route["automatic"] is True
    assert route["arguments"] == {
        "vision": "always",
        "scope": "desktop",
        "max_elements": 180,
    }


def test_recover_after_visual_route_requires_full_replan():
    route = select_recovery_route(
        _output(
            "RECOVER",
            vision_escalated=True,
            evidence_sources=["vision"],
        ),
        {"scope": "foreground"},
    )
    assert route is not None
    assert route["route"] == "full_replan"
    assert route["tool"] is None
    assert route["automatic"] is False
    assert route["requires_different_route"] is True


def test_directive_merges_policy_and_route_reason_codes():
    output = _output("RETRY", uia_actionable=False)
    directive = build_recovery_directive(output, {"scope": "foreground"})
    assert directive is not None
    assert directive["decision"] == "RETRY"
    assert directive["route"] == "foreground_vision"
    assert "verification_not_satisfied" in directive["reason_codes"]
    assert "semantic_retry_needs_stronger_grounding" in directive["reason_codes"]


def test_app_refocus_route_is_selected_but_not_auto_executed(tmp_path, monkeypatch):
    from iras.core.agent import IRASAgent
    from iras.models import ProviderReply, ToolCall, ToolResult

    class Memory:
        def all_facts(self, limit): return []
        def recent_messages(self, limit): return []
        def add_message(self, role, text): pass
        def remember(self, key, value): pass

    class Audit:
        def __init__(self): self.events = []
        def record(self, event, payload): self.events.append((event, payload))

    class Tools:
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
                        "prior_foreground": {"title": "WhatsApp", "hwnd": 10},
                        "observation": {
                            "foreground": {"title": "Windows PowerShell", "hwnd": 20},
                            "uia_actionable": True,
                        },
                        "assessment": {
                            "evidence_sources": ["uia"],
                            "state_delta": {"foreground_changed": True},
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
            raise AssertionError(f"unexpected automatic tool execution: {name}")

    class Provider:
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
            assert any(
                m.get("role") == "system"
                and "app_refocus_reacquire" in str(m.get("content") or "")
                for m in messages
            )
            return ProviderReply(
                "Recovery route selected safely.",
                [],
                {"role": "assistant", "content": "Recovery route selected safely."},
            )

    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tools = Tools()
    audit = Audit()
    agent = IRASAgent(
        provider=Provider(),
        tools=tools,
        memory=Memory(),
        audit=audit,
        smart_tools=True,
    )

    result = agent.handle("Verify my WhatsApp action.")

    assert result == "Recovery route selected safely."
    assert [name for name, _ in tools.calls] == ["device_computer_verify"]
    assert any(
        event == "automatic_outcome_recovery_route_selected"
        and payload.get("route") == "app_refocus_reacquire"
        for event, payload in audit.events
    )
