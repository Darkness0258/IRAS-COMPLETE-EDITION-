from __future__ import annotations

from typing import Any

from iras.device_bridge.fresh_action_planning import validate_fresh_action_call


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_fresh_plan_execution(
    plan: dict[str, Any] | None,
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> tuple[bool, str]:
    """Gate a post-recovery action against the validated fresh plan.

    v3.5.15 does not auto-select or auto-replay an action. It only proves that
    the action chosen by the planner is bound to the fresh recovery observation
    and, when element ids are supplied, to elements that actually came from that
    observation.
    """

    data = _dict(plan)
    if str(tool_name) != "device_computer_action":
        return True, ""

    if data.get("status") != "READY_FOR_FRESH_ACTION_SELECTION":
        return False, "fresh_action_plan_not_ready_for_execution"
    if data.get("action_replay_allowed") is not False:
        return False, "fresh_action_plan_replay_safety_contract_missing"
    if not data.get("requires_post_action_verification"):
        return False, "fresh_action_plan_verification_contract_missing"

    return validate_fresh_action_call(data, tool_name, arguments)


def build_chained_verification_call(
    plan: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the read-only verification call required after a fresh action."""

    data = _dict(plan)
    if data.get("status") != "READY_FOR_FRESH_ACTION_SELECTION":
        return None
    if not data.get("requires_post_action_verification"):
        return None

    contract = _dict(data.get("verification_contract"))
    condition = str(contract.get("condition") or "").strip()
    if not condition:
        return None

    target = str(contract.get("target") or "")
    scope = str(contract.get("scope") or "auto").strip() or "auto"
    observation_id = str(data.get("fresh_observation_id") or "").strip()
    if not observation_id:
        return None

    return {
        "tool": "device_computer_verify",
        "arguments": {
            "condition": condition,
            "target": target,
            "prior_observation_id": observation_id,
            "vision": "auto",
            "scope": scope,
        },
        "automatic": True,
        "state_changing": False,
        "purpose": "verify_fresh_planned_action_semantic_outcome",
        "action_replay_allowed": False,
    }


def chained_verification_message(
    verification_call: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
    decision = output.get("decision") if isinstance(output.get("decision"), dict) else {}
    return (
        "FRESH-ACTION AUTOMATIC VERIFICATION v3.5.15: "
        f"status={output.get('status')!r}; confidence={output.get('confidence')!r}; "
        f"semantic_goal_verified={output.get('semantic_goal_verified')!r}; "
        f"decision={decision.get('action')!r}; goal_sufficient={decision.get('goal_sufficient')!r}; "
        f"verification_arguments={_dict(verification_call.get('arguments'))!r}. "
        "This verification is read-only. The prior state-changing action was not replayed."
    )
