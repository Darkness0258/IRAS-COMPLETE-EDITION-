from __future__ import annotations

from typing import Any


ACCEPT = "ACCEPT"
RETRY = "RETRY"
ESCALATE_VISION = "ESCALATE_VISION"
RECOVER = "RECOVER"

DEFAULT_MAX_RETRIES = 2


def decide_outcome(
    assessment: dict[str, Any],
    *,
    condition: str,
    vision_escalated: bool,
    can_escalate_vision: bool,
    failure_count: int,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, Any]:
    """Convert verification evidence into a bounded next-step decision.

    This policy deliberately separates *condition acceptance* from *goal
    sufficiency*.  A state-only predicate such as ``screen_changed`` may be
    accepted as true while still being insufficient proof of the user's
    semantic end goal.
    """

    condition = str(condition or "").strip().lower()
    failure_count = max(0, int(failure_count or 0))
    max_retries = max(0, int(max_retries or 0))

    verified = bool(assessment.get("condition_verified"))
    semantic_goal_verified = bool(assessment.get("semantic_goal_verified"))
    state_only_verified = bool(assessment.get("state_only_verified"))
    outcome_class = str(assessment.get("outcome_class") or "unknown")
    confidence = float(assessment.get("confidence") or 0.0)
    sources = {str(value) for value in (assessment.get("evidence_sources") or [])}
    reasons = [str(value) for value in (assessment.get("reason_codes") or [])]

    # Absence claims need visual coverage when vision is available. Likewise,
    # failed semantic checks should visually re-ground once before retrying the
    # action itself. This can be returned by the policy and executed by the
    # controller in the same verification call.
    semantic_needs_visual_confirmation = bool(
        outcome_class == "semantic_goal"
        and can_escalate_vision
        and not vision_escalated
        and "vision" not in sources
        and (
            not verified
            or "semantic_absence_without_visual_coverage" in reasons
        )
    )
    if semantic_needs_visual_confirmation:
        return {
            "action": ESCALATE_VISION,
            "goal_sufficient": False,
            "condition_accepted": False,
            "failure_count": failure_count,
            "max_retries": max_retries,
            "retry_budget_remaining": max(0, max_retries - failure_count),
            "reason_codes": ["semantic_target_needs_visual_confirmation"],
        }

    if verified:
        goal_sufficient = bool(
            semantic_goal_verified or outcome_class == "window_state_goal"
        )
        reason_codes = ["verification_condition_accepted"]
        if state_only_verified and not goal_sufficient:
            reason_codes.append("state_only_evidence_not_goal_completion")
        if confidence < 0.70:
            reason_codes.append("accepted_with_low_confidence")
        return {
            "action": ACCEPT,
            "goal_sufficient": goal_sufficient,
            "condition_accepted": True,
            "failure_count": 0,
            "max_retries": max_retries,
            "retry_budget_remaining": max_retries,
            "reason_codes": reason_codes,
        }

    # Failed or inconclusive checks may be retried only within a bounded budget.
    # After that, the caller must re-plan/recover instead of repeating the same
    # route indefinitely.
    if failure_count <= max_retries:
        reason_codes = ["verification_not_satisfied", "bounded_retry_available"]
        state_delta = assessment.get("state_delta") or {}
        if any(
            state_delta.get(key) is True
            for key in ("screen_changed", "visual_changed", "foreground_changed")
        ):
            reason_codes.append("state_changed_without_verified_goal")
        else:
            reason_codes.append("no_verified_goal_change")
        return {
            "action": RETRY,
            "goal_sufficient": False,
            "condition_accepted": False,
            "failure_count": failure_count,
            "max_retries": max_retries,
            "retry_budget_remaining": max(0, max_retries - failure_count + 1),
            "reason_codes": reason_codes,
        }

    return {
        "action": RECOVER,
        "goal_sufficient": False,
        "condition_accepted": False,
        "failure_count": failure_count,
        "max_retries": max_retries,
        "retry_budget_remaining": 0,
        "reason_codes": [
            "verification_not_satisfied",
            "retry_budget_exhausted",
            "reobserve_and_replan_required",
        ],
    }
