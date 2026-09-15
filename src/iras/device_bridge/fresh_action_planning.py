from __future__ import annotations

import re
from typing import Any


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _norm(value: Any) -> str:
    text = str(value or "").casefold().replace("_", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _semantic_score(target: str, label: str) -> float:
    wanted = _norm(target)
    visible = _norm(label)
    if not wanted or not visible:
        return 0.0
    if wanted == visible:
        return 1.0
    if wanted in visible or visible in wanted:
        shorter = min(len(wanted), len(visible))
        longer = max(len(wanted), len(visible))
        return min(0.96, 0.82 + (0.14 * shorter / max(1, longer)))

    wanted_tokens = set(wanted.split())
    visible_tokens = set(visible.split())
    if not wanted_tokens or not visible_tokens:
        return 0.0
    overlap = wanted_tokens & visible_tokens
    if not overlap:
        return 0.0
    coverage = len(overlap) / len(wanted_tokens)
    precision = len(overlap) / len(visible_tokens)
    return round((0.68 * coverage) + (0.22 * precision), 4)


def build_fresh_action_plan(
    handoff: dict[str, Any] | None,
    *,
    verification_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a non-executable fresh-action planning contract.

    v3.5.14 deliberately does not replay the failed action. It binds planning to
    the recovery observation, semantically re-grounds the verification target,
    and exposes only fresh element ids as candidates. A model/planner must still
    choose a new action and that action must be verified afterwards.
    """

    state = _dict(handoff)
    context = _dict(verification_context) or _dict(state.get("verification_context"))
    observation_id = str(state.get("fresh_observation_id") or "")
    target = str(context.get("target") or "").strip()
    condition = str(context.get("condition") or "").strip()
    scope = str(context.get("scope") or "auto").strip() or "auto"
    grounded = state.get("grounded_elements")
    if not isinstance(grounded, list):
        grounded = []

    fresh_elements: list[dict[str, Any]] = []
    allowed_ids: list[str] = []
    for item in grounded:
        if not isinstance(item, dict):
            continue
        element_id = str(item.get("element_id") or "").strip()
        if not element_id:
            continue
        candidate = {
            "element_id": element_id,
            "label": str(item.get("label") or item.get("name") or ""),
            "role": str(item.get("role") or ""),
            "rect": item.get("rect") if isinstance(item.get("rect"), dict) else None,
        }
        fresh_elements.append(candidate)
        allowed_ids.append(element_id)

    base = {
        "version": "3.5.14",
        "fresh_observation_id": observation_id or None,
        "verification_context": {
            "condition": condition or None,
            "target": target or None,
            "scope": scope,
        },
        "action_replay_allowed": False,
        "automatic_state_change_allowed": False,
        "stale_element_ids_allowed": False,
        "allowed_fresh_element_ids": allowed_ids,
        "requires_new_action_choice": True,
        "requires_post_action_verification": True,
        "verification_contract": {
            "tool": "device_computer_verify",
            "condition": condition or None,
            "target": target or None,
            "scope": scope,
        },
        "planner_constraints": [
            "use_fresh_observation_only",
            "use_only_fresh_element_ids",
            "do_not_replay_prior_state_changing_action",
            "choose_action_again_from_current_state",
            "verify_semantic_outcome_after_action",
        ],
    }

    if not state.get("recovery_ok") or not state.get("fresh_state_available") or not observation_id:
        return {
            **base,
            "status": "BLOCKED",
            "reason": "fresh_recovery_state_unavailable",
            "selected_element": None,
            "candidate_elements": [],
            "next_step": "replan_or_report_recovery_failure",
        }

    if state.get("requires_different_route"):
        return {
            **base,
            "status": "REPLAN_REQUIRED",
            "reason": "recovery_route_requires_materially_different_plan",
            "selected_element": None,
            "candidate_elements": [],
            "next_step": "choose_materially_different_route",
        }

    if not target:
        return {
            **base,
            "status": "TARGET_UNSPECIFIED",
            "reason": "verification_target_missing",
            "selected_element": None,
            "candidate_elements": [],
            "next_step": "planner_must_identify_target_from_user_goal",
        }

    scored: list[dict[str, Any]] = []
    for element in fresh_elements:
        score = _semantic_score(target, element["label"])
        if score <= 0:
            continue
        scored.append({**element, "semantic_score": score})
    scored.sort(key=lambda item: (-float(item["semantic_score"]), item["element_id"]))

    strong = [item for item in scored if float(item["semantic_score"]) >= 0.72]
    selected = None
    status = "TARGET_NOT_REGROUNDED"
    reason = "no_fresh_element_semantically_matches_target"
    next_step = "reobserve_or_replan_target_grounding"

    if strong:
        best = strong[0]
        runner_up = strong[1] if len(strong) > 1 else None
        unambiguous = (
            float(best["semantic_score"]) >= 0.98
            and (runner_up is None or float(runner_up["semantic_score"]) < 0.98)
        ) or (
            runner_up is None
            or float(best["semantic_score"]) - float(runner_up["semantic_score"]) >= 0.10
        )
        if unambiguous:
            selected = best
            status = "READY_FOR_FRESH_ACTION_SELECTION"
            reason = "target_regrounded_from_fresh_observation"
            next_step = "planner_choose_new_action_for_selected_fresh_target"
        else:
            status = "AMBIGUOUS_TARGET"
            reason = "multiple_fresh_elements_match_target"
            next_step = "planner_disambiguate_using_fresh_state"

    return {
        **base,
        "status": status,
        "reason": reason,
        "selected_element": selected,
        "candidate_elements": strong[:8],
        "next_step": next_step,
    }


def validate_fresh_action_call(
    plan: dict[str, Any] | None,
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> tuple[bool, str]:
    """Reject stale observation/element ids for a post-recovery computer action."""

    data = _dict(plan)
    args = _dict(arguments)
    if str(tool_name) != "device_computer_action":
        return True, ""

    expected_observation = str(data.get("fresh_observation_id") or "")
    supplied_observation = str(args.get("observation_id") or "")
    if expected_observation and supplied_observation != expected_observation:
        return False, "stale_observation_id_after_recovery"

    allowed = {str(value) for value in (data.get("allowed_fresh_element_ids") or []) if str(value)}
    for key in ("element_id", "target_element_id"):
        value = str(args.get(key) or "").strip()
        if value and value not in allowed:
            return False, "stale_or_unobserved_element_id_after_recovery"

    return True, ""


def fresh_action_plan_message(plan: dict[str, Any]) -> str:
    selected = _dict(plan.get("selected_element"))
    candidates = plan.get("candidate_elements")
    if not isinstance(candidates, list):
        candidates = []
    compact = [
        {
            "element_id": str(item.get("element_id") or ""),
            "label": str(item.get("label") or ""),
            "role": str(item.get("role") or ""),
            "semantic_score": item.get("semantic_score"),
        }
        for item in candidates[:8]
        if isinstance(item, dict)
    ]
    return (
        "RECOVERY-AWARE FRESH ACTION PLAN v3.5.14: "
        f"status={plan.get('status')!r}; reason={plan.get('reason')!r}; "
        f"fresh_observation_id={plan.get('fresh_observation_id')!r}; "
        f"verification_context={plan.get('verification_context')!r}; "
        f"selected_element={selected or None!r}; candidates={compact!r}; "
        f"next_step={plan.get('next_step')!r}. "
        "Only element ids from this fresh observation may be used. Choose the next action again from current state; "
        "do not replay the prior click/type/send/submit/Enter action. After any new state-changing action, run the required semantic verification before claiming success."
    )
