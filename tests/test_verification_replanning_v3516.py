from iras.core.agent import IRASAgent
from iras.device_bridge.verification_replanning import plan_verification_replanning
from iras.models import ProviderReply, ToolCall, ToolResult


def _payload(action="RETRY", *, goal_sufficient=False, vision=False, uia=True):
    return {
        "ok": True,
        "output": {
            "status": "PASS" if action == "ACCEPT" else "FAIL",
            "condition": "text_contains",
            "target": "Darkness",
            "scope": "foreground",
            "semantic_goal_verified": bool(action == "ACCEPT" and goal_sufficient),
            "vision_escalated": vision,
            "prior_foreground": {"title": "WhatsApp", "hwnd": 10},
            "observation": {
                "foreground": {"title": "WhatsApp", "hwnd": 10},
                "uia_actionable": uia,
            },
            "assessment": {
                "evidence_sources": ["vision"] if vision else [],
                "state_delta": {"foreground_changed": False},
            },
            "decision": {
                "action": action,
                "goal_sufficient": goal_sufficient,
                "failure_count": 0 if action == "ACCEPT" else 1,
                "retry_budget_remaining": 2 if action == "ACCEPT" else 1,
                "reason_codes": [
                    "verification_condition_accepted"
                    if action == "ACCEPT"
                    else "verification_not_satisfied"
                ],
            },
        },
        "error": None,
    }


def _args():
    return {
        "condition": "text_contains",
        "target": "Darkness",
        "prior_observation_id": "fresh-3516",
        "vision": "auto",
        "scope": "foreground",
    }


def test_v3516_accept_goal_sufficient_finishes_without_recovery():
    result = plan_verification_replanning(
        _payload("ACCEPT", goal_sufficient=True),
        _args(),
        automatic_recovery_available=True,
    )
    assert result["status"] == "GOAL_COMPLETE"
    assert result["terminal"] is True
    assert result["directive"] is None
    assert result["action_replay_allowed"] is False


def test_v3516_accept_state_only_requires_material_replan():
    result = plan_verification_replanning(
        _payload("ACCEPT", goal_sufficient=False),
        _args(),
        automatic_recovery_available=True,
    )
    assert result["status"] == "MATERIAL_REPLAN_REQUIRED"
    assert result["terminal"] is False
    assert result["requires_materially_different_plan"] is True
    assert result["action_replay_allowed"] is False


def test_v3516_retry_schedules_safe_read_only_recovery():
    result = plan_verification_replanning(
        _payload("RETRY", uia=True),
        _args(),
        automatic_recovery_available=True,
    )
    assert result["status"] == "SAFE_RECOVERY_READY"
    assert result["automatic_recovery_allowed"] is True
    assert result["directive"]["route"] == "uia_reground"
    assert result["directive"]["tool"] == "device_computer_observe"
    assert result["directive"]["state_changing"] is False
    assert result["action_replay_allowed"] is False


def test_v3516_visual_recover_requires_different_planner_route():
    result = plan_verification_replanning(
        _payload("RECOVER", vision=True, uia=False),
        _args(),
        automatic_recovery_available=True,
    )
    assert result["status"] == "PLANNER_ROUTE_REQUIRED"
    assert result["directive"]["route"] == "full_replan"
    assert result["automatic_recovery_allowed"] is False
    assert result["requires_materially_different_plan"] is True


def test_v3516_recovery_budget_exhaustion_forces_replan():
    result = plan_verification_replanning(
        _payload("RETRY", uia=False),
        _args(),
        automatic_recovery_available=False,
    )
    assert result["status"] == "RECOVERY_BUDGET_EXHAUSTED"
    assert result["automatic_recovery_allowed"] is False
    assert result["requires_materially_different_plan"] is True
    assert result["action_replay_allowed"] is False


def test_v3516_verification_tool_failure_never_replays_action():
    result = plan_verification_replanning(
        {"ok": False, "output": None, "error": "boom"},
        _args(),
        automatic_recovery_available=True,
    )
    assert result["status"] == "VERIFICATION_ERROR_REPLAN"
    assert result["action_replay_allowed"] is False
    assert result["automatic_recovery_allowed"] is False


class _Memory:
    def all_facts(self, limit): return []
    def recent_messages(self, limit): return []
    def add_message(self, role, text): pass
    def remember(self, key, value): pass


class _Audit:
    def __init__(self): self.events = []
    def record(self, event, payload): self.events.append((event, payload))


class _ToolsRetryAfterFreshAction:
    def __init__(self):
        self.calls = []
        self.verify_count = 0
        self.observe_count = 0

    def schemas(self, names=None):
        return [{"type": "function", "function": {"name": n}} for n in (names or [])]

    def execute(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if name == "device_computer_verify":
            self.verify_count += 1
            return ToolResult(
                ok=True,
                output={
                    "status": "FAIL",
                    "condition": "text_contains",
                    "target": "Darkness",
                    "scope": "foreground",
                    "vision_escalated": False,
                    "prior_foreground": {"title": "WhatsApp", "hwnd": 42},
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
                        "failure_count": self.verify_count,
                        "retry_budget_remaining": max(0, 2 - self.verify_count),
                        "goal_sufficient": False,
                        "reason_codes": ["verification_not_satisfied"],
                    },
                },
            )
        if name == "device_computer_observe":
            self.observe_count += 1
            obs_id = f"fresh-agent-3516-{self.observe_count}"
            return ToolResult(
                ok=True,
                output={
                    "observation_id": obs_id,
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


class _ProviderRetryAfterFreshAction:
    model = "fake/model"
    last_model = "fake/model"

    def __init__(self): self.calls = 0

    def complete(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return ProviderReply(
                "",
                [ToolCall(
                    "verify-3516",
                    "device_computer_verify",
                    {"condition": "text_contains", "target": "Darkness", "scope": "foreground"},
                )],
                {"role": "assistant", "content": ""},
            )
        if self.calls == 2:
            system_text = "\n".join(
                str(m.get("content") or "") for m in messages if m.get("role") == "system"
            )
            assert "fresh-agent-3516-1" in system_text
            return ProviderReply(
                "",
                [ToolCall(
                    "fresh-action-3516",
                    "device_computer_action",
                    {
                        "observation_id": "fresh-agent-3516-1",
                        "action": "click",
                        "element_id": "vision:7",
                    },
                )],
                {"role": "assistant", "content": ""},
            )

        system_text = "\n".join(
            str(m.get("content") or "") for m in messages if m.get("role") == "system"
        )
        assert "VERIFICATION-RESULT-DRIVEN REPLANNING v3.5.16" in system_text
        assert "fresh-agent-3516-2" in system_text
        assert "action_replay_allowed=False" in system_text
        return ProviderReply(
            "Fresh action failed verification and IRAS safely reacquired state for replanning.",
            [],
            {
                "role": "assistant",
                "content": "Fresh action failed verification and IRAS safely reacquired state for replanning.",
            },
        )


def test_v3516_agent_uses_chained_failure_to_schedule_next_safe_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tools = _ToolsRetryAfterFreshAction()
    audit = _Audit()
    agent = IRASAgent(
        provider=_ProviderRetryAfterFreshAction(),
        tools=tools,
        memory=_Memory(),
        audit=audit,
        smart_tools=True,
    )

    result = agent.handle("Verify Darkness is visible in WhatsApp.")

    assert result == "Fresh action failed verification and IRAS safely reacquired state for replanning."
    assert [name for name, _ in tools.calls] == [
        "device_computer_verify",
        "device_computer_observe",
        "device_computer_action",
        "device_computer_verify",
        "device_computer_observe",
    ]
    transitions = [
        payload for event, payload in audit.events
        if event == "fresh_action_verification_replanning"
    ]
    assert transitions
    assert transitions[0]["transition"]["status"] == "SAFE_RECOVERY_READY"
    recoveries = [
        payload for event, payload in audit.events
        if event == "fresh_action_verification_automatic_recovery"
    ]
    assert recoveries
    assert recoveries[0]["handoff"]["fresh_observation_id"] == "fresh-agent-3516-2"
    assert recoveries[0]["action_replay_allowed"] is False


class _ToolsAcceptAfterFreshAction(_ToolsRetryAfterFreshAction):
    def execute(self, name, arguments):
        if name == "device_computer_verify" and self.verify_count >= 1:
            self.calls.append((name, dict(arguments)))
            self.verify_count += 1
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
        return super().execute(name, arguments)


def test_v3516_chained_accept_marks_goal_complete_without_extra_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tools = _ToolsAcceptAfterFreshAction()
    audit = _Audit()
    agent = IRASAgent(
        provider=_ProviderRetryAfterFreshAction(),
        tools=tools,
        memory=_Memory(),
        audit=audit,
        smart_tools=True,
    )

    # The provider's third-turn assertions expect a second recovery, so for the
    # ACCEPT branch use a tiny provider that only checks the transition message.
    class AcceptProvider(_ProviderRetryAfterFreshAction):
        def complete(self, messages, schemas):
            self.calls += 1
            if self.calls == 1:
                return ProviderReply(
                    "",
                    [ToolCall(
                        "verify-accept-3516",
                        "device_computer_verify",
                        {"condition": "text_contains", "target": "Darkness", "scope": "foreground"},
                    )],
                    {"role": "assistant", "content": ""},
                )
            if self.calls == 2:
                return ProviderReply(
                    "",
                    [ToolCall(
                        "fresh-action-accept-3516",
                        "device_computer_action",
                        {
                            "observation_id": "fresh-agent-3516-1",
                            "action": "click",
                            "element_id": "vision:7",
                        },
                    )],
                    {"role": "assistant", "content": ""},
                )
            system_text = "\n".join(
                str(m.get("content") or "") for m in messages if m.get("role") == "system"
            )
            assert "status='GOAL_COMPLETE'" in system_text
            return ProviderReply(
                "Fresh action verified and goal complete.",
                [],
                {"role": "assistant", "content": "Fresh action verified and goal complete."},
            )

    agent.provider = AcceptProvider()
    result = agent.handle("Verify Darkness is visible in WhatsApp.")
    assert result == "Fresh action verified and goal complete."
    assert [name for name, _ in tools.calls] == [
        "device_computer_verify",
        "device_computer_observe",
        "device_computer_action",
        "device_computer_verify",
    ]
    transitions = [
        payload for event, payload in audit.events
        if event == "fresh_action_verification_replanning"
    ]
    assert transitions[-1]["transition"]["status"] == "GOAL_COMPLETE"
    assert transitions[-1]["transition"]["action_replay_allowed"] is False
