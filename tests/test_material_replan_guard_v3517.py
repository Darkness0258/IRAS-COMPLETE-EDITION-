from __future__ import annotations

from iras.device_bridge.replan_guard import (
    material_replan_contract,
    recovery_route_cycle_guard,
    recovery_route_signature,
    tool_call_signature,
)
from iras.device_bridge.task_engine import TaskTracker


def _directive(scope: str = "foreground") -> dict:
    return {
        "decision": "RETRY",
        "route": "foreground_vision" if scope == "foreground" else "desktop_vision",
        "tool": "device_computer_observe",
        "arguments": {"vision": "always", "scope": scope, "max_elements": 180},
        "automatic": True,
        "state_changing": False,
        "requires_different_route": False,
        "reason_codes": ["validation"],
    }


def _payload(obs: str = "obs") -> dict:
    return {
        "ok": True,
        "output": {
            "observation_id": obs,
            "foreground": {"title": "WhatsApp", "hwnd": 1},
            "vision_scope": "foreground",
            "uia_actionable": False,
            "elements": [],
        },
        "error": None,
    }


def test_v3517_route_signature_is_deterministic():
    left = _directive()
    right = _directive()
    right["arguments"] = {"scope": "foreground", "max_elements": 180, "vision": "always"}
    assert recovery_route_signature(left) == recovery_route_signature(right)


def test_v3517_two_identical_recoveries_are_bounded_but_third_is_cycle():
    directive = _directive()
    sig = recovery_route_signature(directive)
    history = [
        {"route_signature": sig},
        {"route_signature": sig},
    ]
    guard = recovery_route_cycle_guard(history, directive)
    assert guard["allowed"] is False
    assert guard["previous_uses"] == 2
    assert guard["reason"] == "identical_recovery_route_cycle_detected"
    assert guard["action_replay_allowed"] is False


def test_v3517_tracker_allows_two_identical_routes_then_blocks_third(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tracker = TaskTracker("Find Darkness")
    directive = _directive()

    assert tracker.can_execute_automatic_recovery(directive) is True
    tracker.record_automatic_recovery(directive, _payload("obs-1"))
    assert tracker.can_execute_automatic_recovery(directive) is True
    tracker.record_automatic_recovery(directive, _payload("obs-2"))

    guard = tracker.automatic_recovery_guard(directive)
    assert guard["allowed"] is False
    assert guard["previous_uses"] == 2


def test_v3517_material_replan_blocks_exhausted_tool_call(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tracker = TaskTracker("Find Darkness")
    directive = _directive()
    tracker.record_automatic_recovery(directive, _payload("obs-1"))
    tracker.record_automatic_recovery(directive, _payload("obs-2"))

    contract = tracker.require_material_replan(
        directive=directive,
        reason_codes=["identical_recovery_route_cycle_detected"],
    )
    allowed, reason = tracker.before_call(
        "device_computer_observe",
        {"vision": "always", "scope": "foreground", "max_elements": 180},
    )
    assert allowed is False
    assert "materially different plan" in reason
    assert contract["required"] is True
    assert "foreground_vision" in contract["exhausted_routes"]


def test_v3517_different_recovery_route_is_allowed_and_clears_guard_on_success(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tracker = TaskTracker("Find Darkness")
    foreground = _directive("foreground")
    tracker.record_automatic_recovery(foreground, _payload("obs-1"))
    tracker.record_automatic_recovery(foreground, _payload("obs-2"))
    tracker.require_material_replan(
        directive=foreground,
        reason_codes=["identical_recovery_route_cycle_detected"],
    )

    different_args = {"vision": "always", "scope": "desktop", "max_elements": 180}
    allowed, reason = tracker.before_call("device_computer_observe", different_args)
    assert allowed is True
    assert reason == ""
    tracker.record("device_computer_observe", different_args, _payload("obs-3"))
    assert tracker.material_replan_required is False
    assert tracker.recovery_loop_terminated is False


def test_v3517_contract_forbids_only_exhausted_signatures():
    fg = _directive("foreground")
    desktop = _directive("desktop")
    history = []
    for i in range(2):
        history.append({
            "route": fg["route"],
            "route_signature": recovery_route_signature(fg),
            "tool_signature": tool_call_signature(fg["tool"], fg["arguments"]),
        })
    history.append({
        "route": desktop["route"],
        "route_signature": recovery_route_signature(desktop),
        "tool_signature": tool_call_signature(desktop["tool"], desktop["arguments"]),
    })

    contract = material_replan_contract(history)
    assert tool_call_signature(fg["tool"], fg["arguments"]) in contract["forbidden_tool_signatures"]
    assert tool_call_signature(desktop["tool"], desktop["arguments"]) not in contract["forbidden_tool_signatures"]
    assert contract["action_replay_allowed"] is False
