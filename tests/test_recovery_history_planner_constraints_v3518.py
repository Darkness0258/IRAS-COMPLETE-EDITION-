from __future__ import annotations

from iras.device_bridge.replan_guard import (
    material_replan_contract,
    materially_different_replan_message,
    recovery_history_planner_constraints,
    recovery_history_planner_message,
    recovery_route_signature,
    tool_call_signature,
)
from iras.device_bridge.task_engine import TaskTracker


def _directive(route: str, scope: str) -> dict:
    return {
        "decision": "RETRY",
        "route": route,
        "tool": "device_computer_observe",
        "arguments": {"vision": "always", "scope": scope, "max_elements": 180},
        "automatic": True,
        "state_changing": False,
        "reason_codes": ["validation"],
    }


def _entry(directive: dict, step: int, ok: bool) -> dict:
    return {
        "route": directive["route"],
        "route_signature": recovery_route_signature(directive),
        "tool": directive["tool"],
        "tool_signature": tool_call_signature(directive["tool"], directive["arguments"]),
        "automatic_step": step,
        "ok": ok,
    }


def _payload(obs: str, *, ok: bool = True) -> dict:
    return {
        "ok": ok,
        "output": {
            "observation_id": obs,
            "foreground": {"title": "WhatsApp", "hwnd": 1},
            "vision_scope": "foreground",
            "uia_actionable": False,
            "elements": [],
        } if ok else None,
        "error": None if ok else "validation failure",
    }


def test_v3518_constraints_expose_exhausted_failures_and_successful_alternatives():
    fg = _directive("foreground_vision", "foreground")
    desktop = _directive("desktop_vision", "desktop")
    uia = {
        **_directive("uia_reground", "foreground"),
        "arguments": {"vision": "off", "scope": "foreground", "max_elements": 180},
    }
    history = [
        _entry(fg, 1, True),
        _entry(fg, 2, True),
        _entry(uia, 3, False),
        _entry(desktop, 4, True),
    ]
    constraints = recovery_history_planner_constraints(
        history,
        exhausted_routes=["foreground_vision"],
        forbidden_tool_signatures=[tool_call_signature(fg["tool"], fg["arguments"])],
    )

    assert constraints["version"] == "3.5.18"
    assert constraints["exhausted_routes"] == ["foreground_vision"]
    assert constraints["route_use_counts"]["foreground_vision"] == 2
    assert constraints["recent_failed_routes"] == ["uia_reground"]
    assert constraints["successful_alternatives"][0]["route"] == "desktop_vision"
    assert "foreground_vision" not in {
        item["route"] for item in constraints["successful_alternatives"]
    }
    assert constraints["action_replay_allowed"] is False


def test_v3518_saturated_route_is_visible_before_controller_cycle_block():
    fg = _directive("foreground_vision", "foreground")
    constraints = recovery_history_planner_constraints(
        [_entry(fg, 1, True), _entry(fg, 2, True)]
    )
    assert constraints["saturated_routes"] == ["foreground_vision"]
    assert constraints["exhausted_routes"] == []


def test_v3518_material_replan_contract_embeds_planner_constraints():
    fg = _directive("foreground_vision", "foreground")
    desktop = _directive("desktop_vision", "desktop")
    history = [_entry(fg, 1, True), _entry(fg, 2, True), _entry(desktop, 3, True)]
    contract = material_replan_contract(
        history,
        blocked_directive=fg,
        reason_codes=["identical_recovery_route_cycle_detected"],
    )
    planner = contract["planner_constraints"]
    assert contract["version"] == "3.5.18"
    assert "foreground_vision" in planner["exhausted_routes"]
    assert planner["successful_alternatives"][0]["route"] == "desktop_vision"
    assert planner["action_replay_allowed"] is False


def test_v3518_tracker_exposes_history_context_for_next_planner_turn(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_SKILL_STORE", str(tmp_path / "skills.json"))
    tracker = TaskTracker("Find Darkness")
    fg = _directive("foreground_vision", "foreground")
    desktop = _directive("desktop_vision", "desktop")

    tracker.record_automatic_recovery(fg, _payload("obs-1"))
    tracker.record_automatic_recovery(fg, _payload("obs-2"))
    tracker.record_automatic_recovery(desktop, _payload("obs-3"))
    tracker.require_material_replan(
        directive=fg,
        reason_codes=["identical_recovery_route_cycle_detected"],
    )

    constraints = tracker.recovery_planner_constraints()
    assert constraints["exhausted_routes"] == ["foreground_vision"]
    assert constraints["successful_alternatives"][0]["route"] == "desktop_vision"
    assert tracker.audit_summary()["recovery_planner_constraints"] == constraints


def test_v3518_planner_message_is_compact_and_no_replay():
    constraints = {
        "exhausted_routes": ["foreground_vision"],
        "recent_failed_routes": ["uia_reground"],
        "successful_alternatives": [{"route": "desktop_vision"}],
        "saturated_routes": [],
        "route_use_counts": {"foreground_vision": 2, "desktop_vision": 1},
    }
    message = recovery_history_planner_message(constraints)
    assert "RECOVERY-HISTORY-AWARE PLANNER CONSTRAINTS v3.5.18" in message
    assert "foreground_vision" in message
    assert "desktop_vision" in message
    assert "uia_reground" in message
    assert "action_replay_allowed=False" in message


def test_v3518_material_replan_message_feeds_history_to_planner():
    fg = _directive("foreground_vision", "foreground")
    desktop = _directive("desktop_vision", "desktop")
    history = [_entry(fg, 1, True), _entry(fg, 2, True), _entry(desktop, 3, True)]
    contract = material_replan_contract(history, blocked_directive=fg)
    message = materially_different_replan_message(contract)
    assert "MATERIALLY-DIFFERENT REPLAN GUARD" in message
    assert "RECOVERY-HISTORY-AWARE PLANNER CONSTRAINTS v3.5.18" in message
    assert "desktop_vision" in message
    assert "action_replay_allowed=False" in message


def test_v3518_agent_injects_history_context_after_automatic_recovery():
    from pathlib import Path

    source = Path("src/iras/core/agent.py").read_text(encoding="utf-8")
    assert source.count("task_tracker.recovery_planner_message()") >= 2
