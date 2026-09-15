from __future__ import annotations

import json

from iras.device_bridge.adaptive_recovery import rank_recovery_routes
from iras.device_bridge.recovery_learning import (
    RecoveryRoutePerformanceStore,
    recovery_learning_context_from_verification,
    recovery_learning_context_key,
)
from iras.device_bridge.recovery_runtime import build_recovery_directive, select_recovery_route
from iras.device_bridge.task_engine import TaskTracker


def _verification(app: str, *, uia_actionable: bool = True):
    title = {
        "whatsapp": "WhatsApp",
        "spotify": "Spotify Free",
        "notepad": "Untitled - Notepad",
    }[app]
    return {
        "status": "FAIL",
        "condition": "text_contains",
        "scope": "foreground",
        "vision_escalated": False,
        "prior_foreground": {"title": title, "hwnd": 10},
        "observation": {
            "foreground": {"title": title, "hwnd": 10},
            "uia_actionable": uia_actionable,
            "vision_scope": None,
        },
        "assessment": {
            "evidence_sources": ["uia"] if uia_actionable else [],
            "state_delta": {"foreground_changed": False},
        },
        "decision": {
            "action": "RETRY",
            "goal_sufficient": False,
            "failure_count": 1,
            "retry_budget_remaining": 1,
            "reason_codes": ["verification_not_satisfied"],
        },
    }


def _verify_payload(*, success: bool):
    return {
        "ok": True,
        "output": {
            "status": "PASS" if success else "FAIL",
            "semantic_goal_verified": success,
            "decision": {
                "action": "ACCEPT" if success else "RETRY",
                "goal_sufficient": success,
                "failure_count": 0 if success else 1,
                "retry_budget_remaining": 2 if success else 1,
            },
        },
        "error": None,
    }


def _recovery_payload(title: str):
    return {
        "ok": True,
        "output": {
            "observation_id": "ctx-fresh",
            "foreground": {"title": title, "hwnd": 1},
            "vision_scope": "foreground",
            "uia_actionable": False,
            "elements": [],
        },
        "error": None,
    }


def test_v3521_context_key_is_coarse_and_unknown_titles_do_not_persist_user_content():
    output = _verification("whatsapp", uia_actionable=False)
    context = recovery_learning_context_from_verification(output, {"condition": "text_contains"})
    assert context == {
        "app": "whatsapp",
        "uia_actionable": "0",
        "vision_scope": "none",
        "semantic": "1",
    }
    assert "whatsapp" in recovery_learning_context_key(context)

    output["observation"]["foreground"]["title"] = "Secret Project Plan.txt - Custom Editor"
    unknown = recovery_learning_context_from_verification(output, {})
    assert unknown["app"] == "unknown"
    assert "Secret" not in recovery_learning_context_key(unknown)


def test_v3521_store_persists_global_fallback_and_separate_context_priors(tmp_path):
    path = tmp_path / "learning.json"
    store = RecoveryRoutePerformanceStore(path)
    whatsapp = {
        "app": "whatsapp",
        "uia_actionable": False,
        "vision_scope": "none",
        "semantic": True,
    }
    spotify = {
        "app": "spotify",
        "uia_actionable": True,
        "vision_scope": "none",
        "semantic": True,
    }
    store.record("foreground_vision", success=True, context=whatsapp)
    store.record("uia_reground", success=True, context=spotify)

    global_prior = store.snapshot()
    assert global_prior["foreground_vision"]["success_weight"] == 1.0
    assert global_prior["uia_reground"]["success_weight"] == 1.0

    wa = store.context_snapshot(whatsapp)
    sp = store.context_snapshot(spotify)
    assert set(wa["routes"]) == {"foreground_vision"}
    assert set(sp["routes"]) == {"uia_reground"}

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == "3.6.0"
    assert "contexts" in raw
    serialized = json.dumps(raw).lower()
    assert "target" not in serialized
    assert "message" not in serialized
    assert "coordinate" not in serialized


def test_v3521_build_directive_attaches_privacy_bounded_learning_context():
    output = _verification("whatsapp", uia_actionable=False)
    directive = build_recovery_directive(output, {"condition": "text_contains"})
    assert directive is not None
    assert directive["learning_context"]["app"] == "whatsapp"
    assert directive["learning_context"]["uia_actionable"] == "0"
    assert directive["learning_context"]["semantic"] == "1"
    assert "target" not in directive["learning_context"]


def test_v3521_tracker_credits_semantic_result_to_matching_context(tmp_path):
    store = RecoveryRoutePerformanceStore(tmp_path / "tracker.json")
    tracker = TaskTracker("Find Darkness", recovery_performance_store=store)
    output = _verification("whatsapp", uia_actionable=False)
    directive = build_recovery_directive(output, {"condition": "text_contains"})
    assert directive is not None
    tracker.record_automatic_recovery(directive, _recovery_payload("WhatsApp"))
    assert store.snapshot() == {}

    tracker.record(
        "device_computer_verify",
        {"condition": "text_contains", "target": "Darkness"},
        _verify_payload(success=True),
    )
    context_prior = store.context_snapshot(directive["learning_context"])
    assert context_prior["routes"][directive["route"]]["success_weight"] == 1.0
    assert tracker.recovery_learning_pending_context == {}


def test_v3521_planner_constraints_expose_context_priors_without_action_replay(tmp_path):
    store = RecoveryRoutePerformanceStore(tmp_path / "planner.json")
    context = {
        "app": "whatsapp",
        "uia_actionable": False,
        "vision_scope": "none",
        "semantic": True,
    }
    store.record("foreground_vision", success=True, context=context)
    tracker = TaskTracker("Find Darkness", recovery_performance_store=store)
    constraints = tracker.recovery_planner_constraints()
    assert constraints["learned_route_priors_version"] == "3.6.0"
    assert constraints["learned_context_route_priors_version"] == "3.6.0"
    assert constraints["learned_context_route_priors"]
    assert constraints["action_replay_allowed"] is False


def test_v3521_context_prior_applies_only_to_matching_app_state(tmp_path):
    store = RecoveryRoutePerformanceStore(tmp_path / "isolation.json")
    wa_output = _verification("whatsapp", uia_actionable=True)
    sp_output = _verification("spotify", uia_actionable=True)
    args = {"condition": "text_contains", "scope": "foreground"}
    wa_context = recovery_learning_context_from_verification(wa_output, args)

    # Build enough WhatsApp-specific evidence to create a visible contextual
    # nudge while keeping global evidence neutral between the two routes.
    for _ in range(6):
        store.record("foreground_vision", success=True, context=wa_context)
        store.record("uia_reground", success=False, context=wa_context)
    # Offset global statistics with opposite outcomes in Spotify context.
    sp_context = recovery_learning_context_from_verification(sp_output, args)
    for _ in range(6):
        store.record("foreground_vision", success=False, context=sp_context)
        store.record("uia_reground", success=True, context=sp_context)

    constraints = {
        "learned_route_priors": store.snapshot(),
        "learned_context_route_priors": store.context_snapshot(),
    }
    wa_ranked = rank_recovery_routes(
        wa_output,
        args,
        constraints,
        preferred_route=select_recovery_route(wa_output, args),
    )
    sp_ranked = rank_recovery_routes(
        sp_output,
        args,
        constraints,
        preferred_route=select_recovery_route(sp_output, args),
    )
    wa_scores = {x["route"]: x for x in wa_ranked["rankings"]}
    sp_scores = {x["route"]: x for x in sp_ranked["rankings"]}

    assert wa_ranked["learning_context"]["app"] == "whatsapp"
    assert sp_ranked["learning_context"]["app"] == "spotify"
    assert wa_ranked["context_prior_available"] is True
    assert sp_ranked["context_prior_available"] is True
    assert any(
        "contextual_route_prior_adjustment" in reason
        for reason in wa_scores["foreground_vision"]["history_reasons"]
    )
    assert wa_scores["foreground_vision"]["score"] > sp_scores["foreground_vision"]["score"]
    assert sp_scores["uia_reground"]["score"] > wa_scores["uia_reground"]["score"]
    assert wa_ranked["action_replay_allowed"] is False
    assert sp_ranked["action_replay_allowed"] is False


def test_v3521_unknown_context_falls_back_to_global_prior_only(tmp_path):
    store = RecoveryRoutePerformanceStore(tmp_path / "fallback.json")
    wa_context = {
        "app": "whatsapp",
        "uia_actionable": True,
        "vision_scope": "none",
        "semantic": True,
    }
    store.record("foreground_vision", success=True, context=wa_context)

    output = _verification("notepad", uia_actionable=True)
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
    assert ranked["learning_context"]["app"] == "notepad"
    assert ranked["context_prior_available"] is False
    reasons = [
        reason
        for item in ranked["rankings"]
        for reason in item["history_reasons"]
    ]
    assert not any("contextual_route_prior_adjustment" in reason for reason in reasons)
    assert ranked["persistent_learning_version"] == "3.6.0"
