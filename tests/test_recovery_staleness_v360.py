from iras.device_bridge.adaptive_recovery import rank_recovery_routes
from iras.device_bridge.recovery_learning import RecoveryRoutePerformanceStore
from iras.device_bridge.recovery_runtime import select_recovery_route
from iras.device_bridge.recovery_staleness import assess_recovery_prior_health


def _verification():
    return {
        "status": "FAIL",
        "condition": "text_contains",
        "scope": "foreground",
        "prior_foreground": {"title": "WhatsApp", "hwnd": 1},
        "observation": {
            "foreground": {"title": "WhatsApp", "hwnd": 1},
            "uia_actionable": True,
            "vision_scope": None,
        },
        "assessment": {"evidence_sources": ["uia"], "state_delta": {"foreground_changed": False}},
        "decision": {
            "action": "RETRY",
            "goal_sufficient": False,
            "failure_count": 1,
            "retry_budget_remaining": 1,
            "reason_codes": ["verification_not_satisfied"],
        },
    }


def test_v360_repeated_context_failures_quarantine_learned_boost_not_live_route(tmp_path):
    store = RecoveryRoutePerformanceStore(tmp_path / "learn.json")
    context = {"app": "whatsapp", "uia_actionable": True, "vision_scope": "none", "semantic": True}
    # Establish a useful historical prior, then simulate an app/UI behavior change.
    for _ in range(8):
        store.record("uia_reground", success=True, context=context)
    for _ in range(3):
        store.record("uia_reground", success=False, context=context)

    context_prior = store.context_snapshot(context)["routes"]["uia_reground"]
    assert context_prior["consecutive_failures"] == 3
    health = assess_recovery_prior_health(store.snapshot()["uia_reground"], context_prior)
    assert health["status"] == "quarantined"
    assert health["learning_multiplier"] == 0.0
    assert health["live_route_blocked"] is False

    output = _verification()
    args = {"condition": "text_contains", "scope": "foreground"}
    ranked = rank_recovery_routes(
        output,
        args,
        {
            "learned_route_priors": store.snapshot(),
            "learned_context_route_priors": store.context_snapshot(),
        },
        preferred_route=select_recovery_route(output, args),
    )
    uia = next(item for item in ranked["rankings"] if item["route"] == "uia_reground")
    assert uia["learning_calibration"]["prior_health"]["status"] == "quarantined"
    assert uia["learning_calibration"]["combined_adjustment"] == 0.0
    assert "uia_reground" in {item["route"] for item in ranked["rankings"]}
    assert ranked["current_state_authoritative"] is True
    assert ranked["action_replay_allowed"] is False


def test_v360_success_resets_failure_streak(tmp_path):
    store = RecoveryRoutePerformanceStore(tmp_path / "reset.json")
    context = {"app": "whatsapp", "uia_actionable": True, "vision_scope": "none", "semantic": True}
    store.record("foreground_vision", success=False, context=context)
    store.record("foreground_vision", success=False, context=context)
    assert store.context_snapshot(context)["routes"]["foreground_vision"]["consecutive_failures"] == 2
    store.record("foreground_vision", success=True, context=context)
    prior = store.context_snapshot(context)["routes"]["foreground_vision"]
    assert prior["consecutive_failures"] == 0
    assert prior["consecutive_successes"] == 1
    assert assess_recovery_prior_health({}, prior)["status"] == "healthy"
