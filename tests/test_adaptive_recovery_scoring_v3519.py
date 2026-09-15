from __future__ import annotations

from iras.device_bridge.adaptive_recovery import (
    adaptive_recovery_message,
    rank_recovery_routes,
)
from iras.device_bridge.recovery_runtime import (
    build_recovery_directive,
    select_recovery_route,
)
from iras.device_bridge.replan_guard import tool_call_signature


def _output(
    action: str = "RETRY",
    *,
    uia_actionable: bool = True,
    vision_escalated: bool = False,
    evidence_sources=None,
    foreground_changed: bool = False,
    prior_title: str = "WhatsApp",
    condition: str = "text_contains",
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


def _rank(output: dict, constraints: dict, arguments=None):
    args = arguments or {"scope": "foreground"}
    preferred = select_recovery_route(output, args)
    return rank_recovery_routes(
        output,
        args,
        constraints,
        preferred_route=preferred,
    )


def test_v3519_live_evidence_keeps_uia_first_without_negative_history():
    result = _rank(_output(), {})
    assert result["version"] == "3.6.0"
    assert result["selected_route"] == "uia_reground"
    assert result["preferred_live_route"] == "uia_reground"
    assert result["rankings"][0]["route"] == "uia_reground"
    assert result["current_state_authoritative"] is True
    assert result["history_is_advisory"] is True
    assert result["action_replay_allowed"] is False


def test_v3519_recent_uia_failure_and_visual_success_can_change_safe_ranking():
    constraints = {
        "recent_failed_routes": ["uia_reground"],
        "route_use_counts": {"uia_reground": 1, "foreground_vision": 1},
        "successful_alternatives": [
            {"route": "foreground_vision", "successes": 2, "failures": 0}
        ],
    }
    result = _rank(_output(), constraints)
    assert result["preferred_live_route"] == "uia_reground"
    assert result["selected_route"] == "foreground_vision"
    scores = {item["route"]: item["score"] for item in result["rankings"]}
    assert scores["foreground_vision"] > scores["uia_reground"]


def test_v3519_exhausted_route_is_hard_excluded_even_if_live_supported():
    output = _output(uia_actionable=False)
    result = _rank(
        output,
        {
            "exhausted_routes": ["foreground_vision"],
            "route_use_counts": {"foreground_vision": 2},
        },
    )
    assert result["preferred_live_route"] == "foreground_vision"
    assert result["selected_route"] != "foreground_vision"
    assert {item["route"] for item in result["rankings"]}.isdisjoint(
        {"foreground_vision"}
    )
    assert {item["route"]: item["reason"] for item in result["excluded"]}[
        "foreground_vision"
    ] == "exhausted_route"



def test_v3519_forbidden_exact_signature_is_hard_excluded():
    output = _output()
    preferred = select_recovery_route(output, {"scope": "foreground"})
    assert preferred is not None
    forbidden = tool_call_signature(preferred["tool"], preferred["arguments"])
    result = _rank(
        output,
        {"forbidden_tool_signatures": [forbidden]},
    )
    assert result["selected_route"] != "uia_reground"
    excluded = {item["route"]: item["reason"] for item in result["excluded"]}
    assert excluded["uia_reground"] == "forbidden_tool_signature"

def test_v3519_saturated_route_is_deprioritized_before_controller_cycle_block():
    constraints = {
        "saturated_routes": ["uia_reground"],
        "route_use_counts": {"uia_reground": 2},
        "successful_alternatives": [
            {"route": "foreground_vision", "successes": 1, "failures": 0}
        ],
    }
    result = _rank(_output(), constraints)
    assert result["selected_route"] == "foreground_vision"
    uia = next(item for item in result["rankings"] if item["route"] == "uia_reground")
    assert "saturated_route_penalty" in uia["history_reasons"]


def test_v3519_known_foreground_drift_preserves_conservative_refocus_route():
    output = _output(foreground_changed=True, prior_title="WhatsApp")
    result = _rank(
        output,
        {"recent_failed_routes": ["desktop_vision"]},
    )
    assert result["selected_route"] == "app_refocus_reacquire"
    top = result["rankings"][0]
    assert top["state_changing"] is True
    assert top["automatic"] is False


def test_v3519_build_directive_uses_adaptive_selected_route_and_embeds_ranking():
    constraints = {
        "recent_failed_routes": ["uia_reground"],
        "route_use_counts": {"uia_reground": 1, "foreground_vision": 1},
        "successful_alternatives": [
            {"route": "foreground_vision", "successes": 2, "failures": 0}
        ],
    }
    directive = build_recovery_directive(
        _output(),
        {"scope": "foreground", "condition": "text_contains", "target": "Darkness"},
        planner_constraints=constraints,
    )
    assert directive is not None
    assert directive["route"] == "foreground_vision"
    assert directive["adaptive_recovery"]["version"] == "3.6.0"
    assert directive["adaptive_recovery"]["selected_route"] == "foreground_vision"
    assert directive["adaptive_recovery"]["action_replay_allowed"] is False
    assert "adaptive_recovery_scoring_selected" in directive["reason_codes"]


def test_v3519_message_exposes_ranking_without_granting_replay():
    result = _rank(_output(), {})
    message = adaptive_recovery_message(result)
    assert "ADAPTIVE RECOVERY ROUTE SCORING v3.6.0" in message
    assert "uia_reground" in message
    assert "action_replay_allowed=False" in message


def test_v3519_agent_wires_history_constraints_into_both_recovery_paths():
    from pathlib import Path

    source = Path("src/iras/core/agent.py").read_text(encoding="utf-8")
    assert source.count("planner_constraints=(") >= 2
    assert source.count("task_tracker.recovery_planner_constraints()") >= 2
