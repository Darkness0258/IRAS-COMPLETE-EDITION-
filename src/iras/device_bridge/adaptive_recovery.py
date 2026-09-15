from __future__ import annotations

from copy import deepcopy
from typing import Any

from iras.device_bridge.replan_guard import tool_call_signature
from iras.device_bridge.recovery_learning import (
    recovery_learning_context_from_verification,
    recovery_learning_context_key,
)
from iras.device_bridge.recovery_calibration import (
    CALIBRATION_VERSION,
    calibrate_route_learning,
    controlled_exploration_bonus,
)
from iras.device_bridge.recovery_staleness import (
    STALENESS_VERSION,
    assess_recovery_prior_health,
    apply_prior_health,
)


READ_ONLY_RECOVERY_TOOL = "device_computer_observe"
SEMANTIC_CONDITIONS = {
    "element_exists",
    "element_absent",
    "text_contains",
    "window_title_contains",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _candidate(
    route: str,
    *,
    tool: str | None,
    arguments: dict[str, Any],
    purpose: str,
    automatic: bool,
    state_changing: bool,
    requires_different_route: bool = False,
    safe_navigation_only: bool = False,
) -> dict[str, Any]:
    return {
        "route": route,
        "tool": tool,
        "arguments": arguments,
        "purpose": purpose,
        "automatic": automatic,
        "state_changing": state_changing,
        "safe_navigation_only": safe_navigation_only,
        "requires_different_route": requires_different_route,
        "reason_codes": [],
    }


def _route_candidates(
    verification_output: dict[str, Any] | None,
    verification_arguments: dict[str, Any] | None,
    preferred_route: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Return only routes that are safe/plausible from current live evidence.

    v3.5.19 intentionally does not let history manufacture a route unsupported by
    current state. History may reorder safe candidates, but live verification
    evidence decides which candidates exist at all.
    """

    output = _dict(verification_output)
    arguments = _dict(verification_arguments)
    decision = _dict(output.get("decision"))
    assessment = _dict(output.get("assessment"))
    state_delta = _dict(assessment.get("state_delta"))
    observation = _dict(output.get("observation"))

    action = str(decision.get("action") or "").strip().upper()
    condition = _norm(output.get("condition") or arguments.get("condition"))
    semantic = condition in SEMANTIC_CONDITIONS
    requested_scope = _norm(arguments.get("scope") or output.get("scope") or "auto")
    if requested_scope not in {"auto", "foreground", "desktop"}:
        requested_scope = "auto"

    reason_codes = {str(v) for v in (decision.get("reason_codes") or [])}
    evidence_sources = {str(v) for v in (assessment.get("evidence_sources") or [])}
    uia_actionable = bool(observation.get("uia_actionable"))
    vision_escalated = bool(output.get("vision_escalated"))
    foreground_changed = state_delta.get("foreground_changed") is True

    candidates: dict[str, dict[str, Any]] = {}

    # Always preserve the deterministic v3.5.12 live-evidence route as a valid
    # candidate. This is especially important for conservative app refocus where
    # the app identity has already been derived safely.
    preferred = _dict(preferred_route)
    if preferred.get("route"):
        candidates[str(preferred["route"])] = deepcopy(preferred)

    if not foreground_changed:
        candidates.setdefault(
            "fresh_observe",
            _candidate(
                "fresh_observe",
                tool=READ_ONLY_RECOVERY_TOOL,
                arguments={
                    "vision": "auto",
                    "scope": requested_scope,
                    "max_elements": 180,
                },
                purpose="fresh_reobservation_before_retry",
                automatic=True,
                state_changing=False,
            ),
        )

    if semantic and not foreground_changed and uia_actionable and not vision_escalated:
        candidates.setdefault(
            "uia_reground",
            _candidate(
                "uia_reground",
                tool=READ_ONLY_RECOVERY_TOOL,
                arguments={"vision": "off", "scope": "foreground", "max_elements": 180},
                purpose="fresh_semantic_uia_regrounding_before_retry",
                automatic=True,
                state_changing=False,
            ),
        )

    if semantic and not foreground_changed:
        candidates.setdefault(
            "foreground_vision",
            _candidate(
                "foreground_vision",
                tool=READ_ONLY_RECOVERY_TOOL,
                arguments={
                    "vision": "always",
                    "scope": "desktop" if requested_scope == "desktop" else "foreground",
                    "max_elements": 180,
                },
                purpose="visual_semantic_regrounding_before_retry",
                automatic=True,
                state_changing=False,
            ),
        )

    # Desktop vision is a safe broad alternative whenever the verification is
    # unresolved. It is intentionally lower-cost-ranked unless drift/desktop
    # scope/RECOVER evidence makes the broad view relevant.
    if action in {"RETRY", "ESCALATE_VISION", "RECOVER"}:
        candidates.setdefault(
            "desktop_vision",
            _candidate(
                "desktop_vision",
                tool=READ_ONLY_RECOVERY_TOOL,
                arguments={"vision": "always", "scope": "desktop", "max_elements": 180},
                purpose="desktop_reacquisition_before_replan",
                automatic=True,
                state_changing=False,
                requires_different_route=(action == "RECOVER"),
            ),
        )

    # Full replan is always a non-executing escape hatch. It receives a high live
    # score only after RECOVER/visual evidence indicates the current grounding
    # family is exhausted.
    candidates.setdefault(
        "full_replan",
        _candidate(
            "full_replan",
            tool=None,
            arguments={},
            purpose="choose_materially_different_plan",
            automatic=False,
            state_changing=False,
            requires_different_route=True,
        ),
    )

    # Keep these values in the ranking function through evidence inspection; no
    # extra candidates are synthesized from historical success alone.
    _ = reason_codes, evidence_sources
    return candidates


def rank_recovery_routes(
    verification_output: dict[str, Any] | None,
    verification_arguments: dict[str, Any] | None,
    planner_constraints: dict[str, Any] | None,
    *,
    preferred_route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rank live-supported recovery routes with bounded historical evidence.

    Hard exclusions (exhausted routes / forbidden exact signatures) are applied
    before scoring. History only nudges ranking; current verification evidence is
    authoritative. State-changing routes may be ranked for planner guidance but
    are never made automatic here.
    """

    output = _dict(verification_output)
    arguments = _dict(verification_arguments)
    constraints = _dict(planner_constraints)
    decision = _dict(output.get("decision"))
    assessment = _dict(output.get("assessment"))
    state_delta = _dict(assessment.get("state_delta"))
    observation = _dict(output.get("observation"))

    action = str(decision.get("action") or "").strip().upper()
    condition = _norm(output.get("condition") or arguments.get("condition"))
    semantic = condition in SEMANTIC_CONDITIONS
    uia_actionable = bool(observation.get("uia_actionable"))
    vision_escalated = bool(output.get("vision_escalated"))
    foreground_changed = state_delta.get("foreground_changed") is True
    reason_codes = {str(v) for v in (decision.get("reason_codes") or [])}
    evidence_sources = {str(v) for v in (assessment.get("evidence_sources") or [])}

    exhausted = {str(v) for v in (constraints.get("exhausted_routes") or []) if str(v)}
    forbidden = {
        str(v) for v in (constraints.get("forbidden_tool_signatures") or []) if str(v)
    }
    recent_failed = {
        str(v) for v in (constraints.get("recent_failed_routes") or []) if str(v)
    }
    saturated = {str(v) for v in (constraints.get("saturated_routes") or []) if str(v)}
    use_counts = {
        str(k): int(v)
        for k, v in _dict(constraints.get("route_use_counts")).items()
    }
    learned_priors = {
        str(route): item
        for route, item in _dict(constraints.get("learned_route_priors")).items()
        if isinstance(item, dict)
    }
    learned_context_priors = {
        str(key): item
        for key, item in _dict(constraints.get("learned_context_route_priors")).items()
        if isinstance(item, dict)
    }
    learning_context = recovery_learning_context_from_verification(output, arguments)
    learning_context_key = recovery_learning_context_key(learning_context)
    context_bucket = _dict(learned_context_priors.get(learning_context_key))
    context_route_priors = {
        str(route): item
        for route, item in _dict(context_bucket.get("routes")).items()
        if isinstance(item, dict)
    }
    successes: dict[str, dict[str, int]] = {}
    for item in constraints.get("successful_alternatives") or []:
        if not isinstance(item, dict):
            continue
        route = str(item.get("route") or "")
        if route:
            successes[route] = {
                "successes": int(item.get("successes") or 0),
                "failures": int(item.get("failures") or 0),
            }

    preferred_name = str(_dict(preferred_route).get("route") or "")
    candidates = _route_candidates(output, arguments, preferred_route)
    rankings: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for route, directive in candidates.items():
        tool = directive.get("tool")
        tool_sig = ""
        if tool:
            tool_sig = tool_call_signature(str(tool), _dict(directive.get("arguments")))
        if route in exhausted:
            excluded.append({"route": route, "reason": "exhausted_route"})
            continue
        if tool_sig and tool_sig in forbidden:
            excluded.append({"route": route, "reason": "forbidden_tool_signature"})
            continue

        score = 10.0
        live_reasons: list[str] = []
        history_reasons: list[str] = []

        if route == preferred_name:
            score += 34
            live_reasons.append("deterministic_live_evidence_preference")

        if route == "uia_reground":
            if semantic and uia_actionable and not foreground_changed:
                score += 34
                live_reasons.append("semantic_uia_actionable")
            if vision_escalated or "semantic_target_needs_visual_confirmation" in reason_codes:
                score -= 35
                live_reasons.append("visual_confirmation_already_required")

        elif route == "foreground_vision":
            if semantic:
                score += 26
                live_reasons.append("semantic_visual_grounding_supported")
            if not uia_actionable:
                score += 24
                live_reasons.append("uia_not_actionable")
            if action == "ESCALATE_VISION" or "semantic_target_needs_visual_confirmation" in reason_codes:
                score += 38
                live_reasons.append("explicit_visual_escalation")
            if vision_escalated or "vision" in evidence_sources:
                score -= 10
                live_reasons.append("vision_already_attempted")

        elif route == "desktop_vision":
            score += 8
            if foreground_changed:
                score += 42
                live_reasons.append("foreground_drift")
            if _norm(arguments.get("scope") or output.get("scope")) == "desktop":
                score += 24
                live_reasons.append("desktop_scope_requested")
            if action == "RECOVER":
                score += 14
                live_reasons.append("broad_recovery_requested")

        elif route == "app_refocus_reacquire":
            if foreground_changed:
                score += 66
                live_reasons.append("known_app_foreground_drift")

        elif route == "fresh_observe":
            if action == "RETRY" and not semantic:
                score += 30
                live_reasons.append("nonsemantic_retry_needs_fresh_state")
            elif action == "RETRY":
                score += 5

        elif route == "full_replan":
            if action == "RECOVER":
                score += 30
                live_reasons.append("recover_policy")
            if vision_escalated or "vision" in evidence_sources:
                score += 30
                live_reasons.append("visual_route_already_attempted")
            if not bool(directive.get("automatic")):
                score -= 3

        uses = int(use_counts.get(route, 0))
        if uses:
            penalty = min(18, uses * 4)
            score -= penalty
            history_reasons.append(f"route_use_penalty:{penalty}")

        if route in recent_failed:
            score -= 28
            history_reasons.append("recent_failure_penalty")

        if route in saturated:
            score -= 48
            history_reasons.append("saturated_route_penalty")

        success = successes.get(route)
        if success:
            bonus = min(24, success["successes"] * 9) - min(9, success["failures"] * 3)
            score += bonus
            history_reasons.append(f"historical_success_adjustment:{bonus}")

        # v3.5.22 calibrates learned evidence before it can influence ranking.
        # Sparse priors are strongly shrunk toward zero; contextual evidence is
        # still stronger than the global fallback, but the combined adjustment
        # remains bounded and can only affect live-supported candidates.
        prior = learned_priors.get(route)
        context_prior = context_route_priors.get(route)
        learning_calibration = calibrate_route_learning(prior, context_prior)
        prior_health = assess_recovery_prior_health(prior, context_prior)
        learning_calibration = apply_prior_health(learning_calibration, prior_health)
        global_adjustment = float(learning_calibration["global"]["adjustment"])
        context_adjustment = float(learning_calibration["context"]["adjustment"])
        combined_learning_adjustment = float(
            learning_calibration["combined_adjustment"]
        )

        if abs(global_adjustment) >= 0.01:
            history_reasons.append(
                f"persistent_route_prior_adjustment:{round(global_adjustment, 2)}"
            )
        if abs(context_adjustment) >= 0.01:
            history_reasons.append(
                "contextual_route_prior_adjustment:"
                f"{round(context_adjustment, 2)}:{learning_context_key}"
            )
        if abs(combined_learning_adjustment) >= 0.01:
            score += combined_learning_adjustment
        history_reasons.append(
            "recovery_learning_confidence:"
            f"{learning_calibration['confidence_level']}:"
            f"{round(float(learning_calibration['combined_confidence']), 2)}"
        )
        for reason in prior_health.get("reason_codes") or []:
            history_reasons.append(str(reason))

        rankings.append(
            {
                "route": route,
                "score": round(score, 2),
                "automatic": bool(directive.get("automatic")),
                "state_changing": bool(directive.get("state_changing")),
                "requires_different_route": bool(directive.get("requires_different_route")),
                "tool": directive.get("tool"),
                "arguments": _dict(directive.get("arguments")),
                "live_reasons": live_reasons,
                "history_reasons": history_reasons,
                "learning_calibration": learning_calibration,
                "exploration_bonus": 0.0,
                "directive": directive,
            }
        )

    # v3.5.22 controlled exploration: only read-only automatic observation
    # routes that are already live-supported and near the best exploitation
    # score can receive a tiny information-gathering bonus. State-changing
    # routes, full replans, exhausted routes, and forbidden signatures can never
    # become eligible through exploration.
    exploration_applied = False
    if rankings:
        provisional_best = max(rankings, key=lambda item: float(item["score"]))
        best_score = float(provisional_best["score"])
        best_cal = _dict(provisional_best.get("learning_calibration"))
        best_samples = float(best_cal.get("effective_samples") or 0.0)
        best_confidence = float(best_cal.get("combined_confidence") or 0.0)
        learning_evidence_present = bool(learned_priors or context_route_priors)
        for item in rankings:
            if item is provisional_best:
                continue
            calibration = _dict(item.get("learning_calibration"))
            exploration = controlled_exploration_bonus(
                candidate_score=float(item["score"]),
                best_score=best_score,
                candidate_effective_samples=float(
                    calibration.get("effective_samples") or 0.0
                ),
                best_effective_samples=best_samples,
                best_learning_confidence=best_confidence,
                automatic=bool(item.get("automatic")),
                state_changing=bool(item.get("state_changing")),
                tool=str(item.get("tool") or ""),
                learning_evidence_present=learning_evidence_present,
            )
            item["exploration"] = exploration
            bonus = float(exploration.get("bonus") or 0.0)
            if exploration.get("allowed") and bonus > 0:
                item["score"] = round(float(item["score"]) + bonus, 2)
                item["exploration_bonus"] = round(bonus, 2)
                item["history_reasons"].append(
                    f"controlled_exploration_bonus:{round(bonus, 2)}"
                )
                exploration_applied = True

    rankings.sort(
        key=lambda item: (
            float(item["score"]),
            not bool(item["state_changing"]),
            bool(item["automatic"]),
            str(item["route"]),
        ),
        reverse=True,
    )

    selected = deepcopy(rankings[0]["directive"]) if rankings else None
    selected_route = str(rankings[0]["route"]) if rankings else ""
    if selected is not None:
        selected["adaptive_score"] = float(rankings[0]["score"])
        selected["adaptive_rank"] = 1
        selected["adaptive_selected"] = True
        selected_reasons = list(selected.get("reason_codes") or [])
        for reason in [
            "adaptive_recovery_scoring_selected",
            *rankings[0]["live_reasons"],
            *rankings[0]["history_reasons"],
        ]:
            if reason and reason not in selected_reasons:
                selected_reasons.append(reason)
        selected["reason_codes"] = selected_reasons

    return {
        "version": "3.6.0",
        "selected_route": selected_route,
        "selected_score": float(rankings[0]["score"]) if rankings else None,
        "preferred_live_route": preferred_name,
        "rankings": [
            {k: v for k, v in item.items() if k != "directive"}
            for item in rankings
        ],
        "excluded": excluded,
        "selected_directive": selected,
        "current_state_authoritative": True,
        "history_is_advisory": True,
        "persistent_learning_version": (
            "3.6.0" if (learned_priors or learned_context_priors) else None
        ),
        "learning_context": learning_context,
        "learning_context_key": learning_context_key,
        "context_prior_available": bool(context_route_priors),
        "calibration_version": CALIBRATION_VERSION,
        "staleness_version": STALENESS_VERSION,
        "controlled_exploration": True,
        "exploration_applied": exploration_applied,
        "action_replay_allowed": False,
    }


def adaptive_recovery_message(result: dict[str, Any] | None) -> str:
    data = _dict(result)
    compact = [
        (str(item.get("route") or ""), item.get("score"))
        for item in (data.get("rankings") or [])[:4]
        if isinstance(item, dict)
    ]
    return (
        "ADAPTIVE RECOVERY ROUTE SCORING v3.6.0: "
        f"selected_route={data.get('selected_route')!r}; "
        f"selected_score={data.get('selected_score')!r}; "
        f"live_preferred_route={data.get('preferred_live_route')!r}; "
        f"ranking={compact!r}; excluded={list(data.get('excluded') or [])!r}. "
        "Current UI evidence is authoritative; calibrated history only reorders live-supported safe routes. "
        "Sparse learning is shrunk toward zero and exploration is limited to safe read-only near-ties. "
        "Exhausted routes and forbidden signatures are hard exclusions. action_replay_allowed=False."
    )
