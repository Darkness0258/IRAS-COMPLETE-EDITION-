from __future__ import annotations

from typing import Any

from iras.device_bridge.recovery_runtime import build_recovery_directive


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def plan_verification_replanning(
    verification_payload: dict[str, Any] | None,
    verification_arguments: dict[str, Any] | None,
    *,
    automatic_recovery_available: bool,
    planner_constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Translate a verification result into the next bounded workflow transition.

    v3.5.16 closes the loop after the automatic verification that follows a
    recovery-aware fresh action. The result can finish the goal, schedule one
    more safe read-only recovery, or require planner-controlled replanning. It
    never grants permission to replay the preceding state-changing action.
    """

    payload = _dict(verification_payload)
    output = _dict(payload.get("output"))
    arguments = _dict(verification_arguments)

    if not payload.get("ok"):
        return {
            "status": "VERIFICATION_ERROR_REPLAN",
            "decision": "",
            "goal_sufficient": False,
            "terminal": False,
            "directive": None,
            "automatic_recovery_allowed": False,
            "requires_materially_different_plan": True,
            "action_replay_allowed": False,
            "reason_codes": ["verification_tool_failed", "fresh_replan_required"],
        }

    decision = _dict(output.get("decision"))
    action = str(decision.get("action") or "").strip().upper()
    goal_sufficient = bool(decision.get("goal_sufficient"))
    semantic_goal_verified = bool(output.get("semantic_goal_verified"))

    if action == "ACCEPT" and goal_sufficient:
        return {
            "status": "GOAL_COMPLETE",
            "decision": action,
            "goal_sufficient": True,
            "semantic_goal_verified": semantic_goal_verified,
            "terminal": True,
            "directive": None,
            "automatic_recovery_allowed": False,
            "requires_materially_different_plan": False,
            "action_replay_allowed": False,
            "reason_codes": ["verification_accepted_goal_sufficient"],
        }

    if action == "ACCEPT" and not goal_sufficient:
        return {
            "status": "MATERIAL_REPLAN_REQUIRED",
            "decision": action,
            "goal_sufficient": False,
            "semantic_goal_verified": semantic_goal_verified,
            "terminal": False,
            "directive": None,
            "automatic_recovery_allowed": False,
            "requires_materially_different_plan": True,
            "action_replay_allowed": False,
            "reason_codes": [
                "verification_condition_accepted_but_goal_insufficient",
                "different_semantic_checkpoint_required",
            ],
        }

    directive = build_recovery_directive(
        output,
        arguments,
        planner_constraints=planner_constraints,
    )
    if directive is None:
        return {
            "status": "MATERIAL_REPLAN_REQUIRED",
            "decision": action,
            "goal_sufficient": False,
            "semantic_goal_verified": semantic_goal_verified,
            "terminal": False,
            "directive": None,
            "automatic_recovery_allowed": False,
            "requires_materially_different_plan": True,
            "action_replay_allowed": False,
            "reason_codes": ["verification_unresolved", "different_plan_required"],
        }

    automatic = directive.get("automatic") is True
    requires_different = bool(directive.get("requires_different_route"))

    if not automatic:
        return {
            "status": "PLANNER_ROUTE_REQUIRED",
            "decision": action,
            "goal_sufficient": False,
            "semantic_goal_verified": semantic_goal_verified,
            "terminal": False,
            "directive": directive,
            "automatic_recovery_allowed": False,
            "requires_materially_different_plan": requires_different,
            "action_replay_allowed": False,
            "reason_codes": list(directive.get("reason_codes") or []),
        }

    if not automatic_recovery_available:
        return {
            "status": "RECOVERY_BUDGET_EXHAUSTED",
            "decision": action,
            "goal_sufficient": False,
            "semantic_goal_verified": semantic_goal_verified,
            "terminal": False,
            "directive": directive,
            "automatic_recovery_allowed": False,
            "requires_materially_different_plan": True,
            "action_replay_allowed": False,
            "reason_codes": [
                *list(directive.get("reason_codes") or []),
                "automatic_recovery_budget_exhausted",
            ],
        }

    return {
        "status": "SAFE_RECOVERY_READY",
        "decision": action,
        "goal_sufficient": False,
        "semantic_goal_verified": semantic_goal_verified,
        "terminal": False,
        "directive": directive,
        "automatic_recovery_allowed": True,
        "requires_materially_different_plan": requires_different,
        "action_replay_allowed": False,
        "reason_codes": list(directive.get("reason_codes") or []),
    }


def verification_replanning_message(transition: dict[str, Any]) -> str:
    data = _dict(transition)
    status = str(data.get("status") or "UNKNOWN")
    decision = str(data.get("decision") or "")
    directive = _dict(data.get("directive"))
    return (
        "VERIFICATION-RESULT-DRIVEN REPLANNING v3.5.16: "
        f"status={status!r}; decision={decision!r}; "
        f"goal_sufficient={bool(data.get('goal_sufficient'))!r}; "
        f"terminal={bool(data.get('terminal'))!r}; "
        f"recovery_route={directive.get('route')!r}; "
        f"requires_materially_different_plan={bool(data.get('requires_materially_different_plan'))!r}; "
        f"reason_codes={list(data.get('reason_codes') or [])!r}. "
        "action_replay_allowed=False. Never replay the prior click/type/send/submit/Enter action automatically."
    )
