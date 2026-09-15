from __future__ import annotations

from typing import Any


STALENESS_VERSION = "3.6.0"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def assess_recovery_prior_health(
    global_prior: dict[str, Any] | None,
    context_prior: dict[str, Any] | None,
) -> dict[str, Any]:
    """Detect when learned recovery behavior has become stale.

    Staleness never blocks a live-supported route. It only attenuates or
    quarantines the *learned adjustment* so stale history cannot overpower
    current UI evidence after an app changes behavior.
    """

    global_p = _dict(global_prior)
    context_p = _dict(context_prior)
    g_fail = _int(global_p.get("consecutive_failures"))
    c_fail = _int(context_p.get("consecutive_failures"))
    g_success = _int(global_p.get("consecutive_successes"))
    c_success = _int(context_p.get("consecutive_successes"))

    status = "healthy"
    multiplier = 1.0
    reasons: list[str] = []

    if c_fail >= 3:
        status = "quarantined"
        multiplier = 0.0
        reasons.append("context_prior_quarantined_after_repeated_verified_failures")
    elif c_fail >= 2:
        status = "degraded"
        multiplier = 0.25
        reasons.append("context_prior_degraded_after_verified_failures")
    elif g_fail >= 4:
        status = "degraded"
        multiplier = 0.5
        reasons.append("global_prior_degraded_after_verified_failures")

    if c_success > 0 and c_fail == 0:
        reasons.append("context_prior_recently_confirmed")
    elif g_success > 0 and g_fail == 0:
        reasons.append("global_prior_recently_confirmed")

    return {
        "version": STALENESS_VERSION,
        "status": status,
        "learning_multiplier": multiplier,
        "global_consecutive_failures": g_fail,
        "context_consecutive_failures": c_fail,
        "global_consecutive_successes": g_success,
        "context_consecutive_successes": c_success,
        "reason_codes": reasons,
        "live_route_blocked": False,
        "action_replay_allowed": False,
    }


def apply_prior_health(
    calibration: dict[str, Any] | None,
    health: dict[str, Any] | None,
) -> dict[str, Any]:
    result = dict(calibration or {})
    info = dict(health or {})
    multiplier = float(info.get("learning_multiplier", 1.0) or 0.0)
    original = float(result.get("combined_adjustment", 0.0) or 0.0)
    result["pre_staleness_adjustment"] = round(original, 6)
    result["combined_adjustment"] = round(original * multiplier, 6)
    result["prior_health"] = info
    result["staleness_version"] = STALENESS_VERSION
    return result
