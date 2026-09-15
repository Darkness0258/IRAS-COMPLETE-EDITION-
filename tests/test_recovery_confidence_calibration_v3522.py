from __future__ import annotations

from iras.device_bridge.adaptive_recovery import rank_recovery_routes
from iras.device_bridge.recovery_calibration import (
    CALIBRATION_VERSION,
    TOTAL_LEARNING_ADJUSTMENT_CAP,
    calibrate_prior,
    calibrate_route_learning,
    controlled_exploration_bonus,
)
from iras.device_bridge.recovery_runtime import select_recovery_route


def _verification(*, uia: bool = True, foreground_changed: bool = False):
    return {
        "status": "FAIL",
        "condition": "text_contains",
        "scope": "foreground",
        "vision_escalated": False,
        "prior_foreground": {"title": "WhatsApp", "hwnd": 10},
        "observation": {
            "foreground": {
                "title": "Spotify Free" if foreground_changed else "WhatsApp",
                "hwnd": 11 if foreground_changed else 10,
            },
            "uia_actionable": uia,
            "vision_scope": None,
        },
        "assessment": {
            "evidence_sources": ["uia"] if uia else [],
            "state_delta": {"foreground_changed": foreground_changed},
        },
        "decision": {
            "action": "RETRY",
            "goal_sufficient": False,
            "failure_count": 1,
            "retry_budget_remaining": 1,
            "reason_codes": ["verification_not_satisfied"],
        },
    }


def _prior(rate: float, samples: float):
    return {
        "success_rate": rate,
        "effective_samples": samples,
        "success_weight": max(0.0, rate * samples),
        "failure_weight": max(0.0, (1.0 - rate) * samples),
    }


def test_v3522_sparse_prior_is_low_confidence_and_strongly_shrunk():
    result = calibrate_prior(_prior(0.9, 1.0), adjustment_cap=7.0, confidence_scale=4.0)
    assert result["confidence_level"] == "low"
    assert 0 < result["adjustment"] < 2.0
    assert result["interval_width"] > 0.5


def test_v3522_mature_prior_has_higher_confidence_and_narrower_interval():
    sparse = calibrate_prior(_prior(0.8, 1.0), adjustment_cap=7.0, confidence_scale=4.0)
    mature = calibrate_prior(_prior(0.8, 16.0), adjustment_cap=7.0, confidence_scale=4.0)
    assert mature["confidence"] > sparse["confidence"]
    assert mature["confidence_level"] == "high"
    assert mature["interval_width"] < sparse["interval_width"]
    assert mature["adjustment"] > sparse["adjustment"]


def test_v3522_combined_learning_adjustment_is_bounded():
    result = calibrate_route_learning(_prior(1.0, 100.0), _prior(1.0, 100.0))
    assert abs(result["combined_adjustment"]) <= TOTAL_LEARNING_ADJUSTMENT_CAP
    assert result["confidence_level"] == "high"
    assert result["version"] == CALIBRATION_VERSION


def test_v3522_controlled_exploration_only_allows_safe_read_only_near_ties():
    safe = controlled_exploration_bonus(
        candidate_score=48.0,
        best_score=50.0,
        candidate_effective_samples=0.5,
        best_effective_samples=5.0,
        best_learning_confidence=0.45,
        automatic=True,
        state_changing=False,
        tool="device_computer_observe",
        learning_evidence_present=True,
    )
    unsafe = controlled_exploration_bonus(
        candidate_score=49.0,
        best_score=50.0,
        candidate_effective_samples=0.0,
        best_effective_samples=5.0,
        best_learning_confidence=0.45,
        automatic=False,
        state_changing=True,
        tool="device_app_control",
        learning_evidence_present=True,
    )
    far = controlled_exploration_bonus(
        candidate_score=20.0,
        best_score=50.0,
        candidate_effective_samples=0.0,
        best_effective_samples=5.0,
        best_learning_confidence=0.45,
        automatic=True,
        state_changing=False,
        tool="device_computer_observe",
        learning_evidence_present=True,
    )
    assert safe["allowed"] is True
    assert safe["bonus"] > 0
    assert unsafe["allowed"] is False
    assert unsafe["bonus"] == 0
    assert far["allowed"] is False


def test_v3522_no_learning_means_no_exploration_perturbation():
    result = controlled_exploration_bonus(
        candidate_score=49.0,
        best_score=50.0,
        candidate_effective_samples=0.0,
        best_effective_samples=0.0,
        best_learning_confidence=0.0,
        automatic=True,
        state_changing=False,
        tool="device_computer_observe",
        learning_evidence_present=False,
    )
    assert result["allowed"] is False
    assert result["bonus"] == 0


def test_v3522_adaptive_ranking_exposes_calibration_and_preserves_hard_exclusion():
    output = _verification(uia=True)
    args = {"condition": "text_contains", "scope": "foreground"}
    preferred = select_recovery_route(output, args)
    constraints = {
        "exhausted_routes": ["foreground_vision"],
        "learned_route_priors": {
            "foreground_vision": _prior(0.99, 32),
            "uia_reground": _prior(0.7, 8),
        },
    }
    result = rank_recovery_routes(output, args, constraints, preferred_route=preferred)
    excluded = {item["route"]: item["reason"] for item in result["excluded"]}
    assert excluded["foreground_vision"] == "exhausted_route"
    assert result["calibration_version"] == "3.6.0"
    assert result["controlled_exploration"] is True
    assert result["current_state_authoritative"] is True
    assert result["action_replay_allowed"] is False
    assert all("learning_calibration" in item for item in result["rankings"])


def test_v3522_foreground_drift_keeps_refocus_nonautomatic_despite_learning():
    output = _verification(uia=True, foreground_changed=True)
    args = {"condition": "text_contains", "scope": "foreground"}
    preferred = select_recovery_route(output, args)
    result = rank_recovery_routes(
        output,
        args,
        {
            "learned_route_priors": {
                "app_refocus_reacquire": _prior(1.0, 32),
                "desktop_vision": _prior(0.0, 32),
            }
        },
        preferred_route=preferred,
    )
    refocus = next(item for item in result["rankings"] if item["route"] == "app_refocus_reacquire")
    assert refocus["state_changing"] is True
    assert refocus["automatic"] is False
    assert refocus["exploration_bonus"] == 0
    assert result["action_replay_allowed"] is False


def test_v3522_sparse_context_evidence_cannot_create_route_or_override_live_safety():
    output = _verification(uia=False)
    args = {"condition": "text_contains", "scope": "foreground"}
    preferred = select_recovery_route(output, args)
    # A context prior for a route not supported by current candidate generation
    # must not manufacture that route into the live plan.
    context_key = "app=whatsapp|uia=0|vision=none|semantic=1"
    result = rank_recovery_routes(
        output,
        args,
        {
            "learned_context_route_priors": {
                context_key: {
                    "routes": {
                        "app_refocus_reacquire": _prior(1.0, 32),
                    }
                }
            }
        },
        preferred_route=preferred,
    )
    routes = {item["route"] for item in result["rankings"]}
    assert "app_refocus_reacquire" not in routes
    assert result["current_state_authoritative"] is True
    assert result["action_replay_allowed"] is False


def test_v3522_ranker_applies_only_bounded_read_only_exploration_to_live_near_tie():
    output = _verification(uia=True)
    args = {"condition": "text_contains", "scope": "foreground"}
    preferred = select_recovery_route(output, args)
    result = rank_recovery_routes(
        output,
        args,
        {
            "recent_failed_routes": ["uia_reground"],
            "route_use_counts": {"uia_reground": 1},
            "successful_alternatives": [
                {"route": "foreground_vision", "successes": 1, "failures": 0}
            ],
            "learned_route_priors": {
                "uia_reground": _prior(0.5, 5.0),
                "foreground_vision": _prior(0.5, 0.5),
            },
        },
        preferred_route=preferred,
    )
    foreground = next(
        item for item in result["rankings"] if item["route"] == "foreground_vision"
    )
    assert result["exploration_applied"] is True
    assert foreground["exploration_bonus"] > 0
    assert foreground["automatic"] is True
    assert foreground["state_changing"] is False
    assert foreground["tool"] == "device_computer_observe"
    assert foreground["exploration_bonus"] <= 2.5
    assert result["action_replay_allowed"] is False
