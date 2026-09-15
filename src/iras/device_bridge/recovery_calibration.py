from __future__ import annotations

import math
from typing import Any


CALIBRATION_VERSION = "3.6.0"
GLOBAL_ADJUSTMENT_CAP = 4.0
CONTEXT_ADJUSTMENT_CAP = 7.0
TOTAL_LEARNING_ADJUSTMENT_CAP = 10.0
EXPLORATION_SCORE_MARGIN = 5.0
MAX_EXPLORATION_BONUS = 2.5


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _prior_stats(prior: dict[str, Any] | None) -> tuple[float, float]:
    raw = prior if isinstance(prior, dict) else {}
    effective = max(0.0, _finite(raw.get("effective_samples"), 0.0))
    rate = min(1.0, max(0.0, _finite(raw.get("success_rate"), 0.5)))
    return effective, rate


def _wilson_interval(rate: float, n: float, z: float = 1.96) -> tuple[float, float]:
    """Return an approximate 95% Wilson interval for weighted evidence.

    Recovery learning uses decayed fractional sample weights. Treating the
    effective weight as ``n`` is intentionally approximate; the interval is a
    calibration signal, not a statistical guarantee.
    """

    if n <= 0:
        return 0.0, 1.0
    denom = 1.0 + (z * z / n)
    center = (rate + (z * z / (2.0 * n))) / denom
    spread = (
        z
        * math.sqrt(max(0.0, (rate * (1.0 - rate) / n) + (z * z / (4.0 * n * n))))
        / denom
    )
    return max(0.0, center - spread), min(1.0, center + spread)


def _confidence_level(confidence: float) -> str:
    if confidence < 0.25:
        return "low"
    if confidence < 0.55:
        return "medium"
    return "high"


def calibrate_prior(
    prior: dict[str, Any] | None,
    *,
    adjustment_cap: float,
    confidence_scale: float,
) -> dict[str, Any]:
    """Convert a learned prior into a bounded, uncertainty-aware adjustment.

    The posterior mean already contains the store's Beta(1,1) smoothing. v3.5.22
    adds a second safeguard: sparse evidence receives low confidence and is
    shrunk strongly toward a zero score adjustment. This prevents one or two
    historical outcomes from dominating live UI evidence.
    """

    effective, rate = _prior_stats(prior)
    scale = max(0.5, float(confidence_scale))
    confidence = effective / (effective + scale) if effective > 0 else 0.0
    low, high = _wilson_interval(rate, effective)
    raw_adjustment = (rate - 0.5) * 2.0 * float(adjustment_cap)
    adjustment = max(
        -float(adjustment_cap),
        min(float(adjustment_cap), raw_adjustment * confidence),
    )
    return {
        "effective_samples": round(effective, 6),
        "success_rate": round(rate, 6),
        "confidence": round(confidence, 6),
        "confidence_level": _confidence_level(confidence),
        "interval_low": round(low, 6),
        "interval_high": round(high, 6),
        "interval_width": round(high - low, 6),
        "adjustment": round(adjustment, 6),
    }


def calibrate_route_learning(
    global_prior: dict[str, Any] | None,
    context_prior: dict[str, Any] | None,
) -> dict[str, Any]:
    """Blend global/context evidence without allowing learned history to dominate."""

    global_result = calibrate_prior(
        global_prior,
        adjustment_cap=GLOBAL_ADJUSTMENT_CAP,
        confidence_scale=6.0,
    )
    context_result = calibrate_prior(
        context_prior,
        adjustment_cap=CONTEXT_ADJUSTMENT_CAP,
        confidence_scale=4.0,
    )
    combined = global_result["adjustment"] + context_result["adjustment"]
    combined = max(
        -TOTAL_LEARNING_ADJUSTMENT_CAP,
        min(TOTAL_LEARNING_ADJUSTMENT_CAP, combined),
    )

    global_n = float(global_result["effective_samples"])
    context_n = float(context_result["effective_samples"])
    total_n = global_n + context_n
    if total_n > 0:
        combined_confidence = (
            global_result["confidence"] * global_n
            + context_result["confidence"] * context_n
        ) / total_n
    else:
        combined_confidence = 0.0

    return {
        "version": CALIBRATION_VERSION,
        "global": global_result,
        "context": context_result,
        "combined_adjustment": round(combined, 6),
        "combined_confidence": round(combined_confidence, 6),
        "confidence_level": _confidence_level(combined_confidence),
        "effective_samples": round(total_n, 6),
    }


def controlled_exploration_bonus(
    *,
    candidate_score: float,
    best_score: float,
    candidate_effective_samples: float,
    best_effective_samples: float,
    best_learning_confidence: float,
    automatic: bool,
    state_changing: bool,
    tool: str | None,
    learning_evidence_present: bool,
) -> dict[str, Any]:
    """Return a tiny deterministic exploration bonus for safe near-ties only.

    Exploration is never a license to create a route, bypass a controller guard,
    or execute a state-changing action. It is available only to read-only
    ``device_computer_observe`` candidates that are already live-supported and
    within a small score margin of the current best. It also requires existing
    learning evidence so a brand-new installation follows deterministic live
    evidence without exploratory perturbation.
    """

    gap = max(0.0, float(best_score) - float(candidate_score))
    allowed = (
        bool(learning_evidence_present)
        and bool(automatic)
        and not bool(state_changing)
        and str(tool or "") == "device_computer_observe"
        and gap <= EXPLORATION_SCORE_MARGIN
        and float(candidate_effective_samples) + 0.25 < float(best_effective_samples)
        and float(best_learning_confidence) < 0.75
    )
    if not allowed:
        return {
            "allowed": False,
            "bonus": 0.0,
            "reason": "exploration_not_eligible",
            "score_gap": round(gap, 6),
        }

    uncertainty = max(0.0, 1.0 - min(1.0, float(best_learning_confidence)))
    sample_gap = max(
        0.0,
        float(best_effective_samples) - float(candidate_effective_samples),
    )
    sample_factor = min(1.0, sample_gap / 6.0)
    margin_factor = max(0.0, 1.0 - (gap / EXPLORATION_SCORE_MARGIN))
    bonus = MAX_EXPLORATION_BONUS * uncertainty * sample_factor * margin_factor
    return {
        "allowed": bonus >= 0.05,
        "bonus": round(max(0.0, min(MAX_EXPLORATION_BONUS, bonus)), 6),
        "reason": "safe_read_only_near_tie_exploration" if bonus >= 0.05 else "exploration_too_small",
        "score_gap": round(gap, 6),
    }
