from __future__ import annotations

import json

from iras.device_bridge.adaptive_recovery import rank_recovery_routes
from iras.device_bridge.recovery_learning import (
    RecoveryRoutePerformanceStore,
    learned_route_prior_message,
)
from iras.device_bridge.recovery_runtime import select_recovery_route
from iras.device_bridge.task_engine import TaskTracker


class Clock:
    def __init__(self, value: float = 1000.0):
        self.value = value

    def __call__(self) -> float:
        return self.value


def _verification_output(*, action: str = "RETRY", uia_actionable: bool = True):
    return {
        "status": "FAIL",
        "condition": "text_contains",
        "scope": "foreground",
        "vision_escalated": False,
        "prior_foreground": {"title": "WhatsApp", "hwnd": 10},
        "observation": {
            "foreground": {"title": "WhatsApp", "hwnd": 10},
            "uia_actionable": uia_actionable,
        },
        "assessment": {
            "evidence_sources": [],
            "state_delta": {"foreground_changed": False},
        },
        "decision": {
            "action": action,
            "goal_sufficient": False,
            "failure_count": 1,
            "retry_budget_remaining": 1,
            "reason_codes": ["verification_not_satisfied"],
        },
    }


def _directive(route: str = "foreground_vision") -> dict:
    return {
        "decision": "RETRY",
        "route": route,
        "tool": "device_computer_observe",
        "arguments": {"vision": "always", "scope": "foreground", "max_elements": 180},
        "automatic": True,
        "state_changing": False,
        "reason_codes": ["validation"],
    }


def _recovery_payload(obs: str = "obs-1") -> dict:
    return {
        "ok": True,
        "output": {
            "observation_id": obs,
            "foreground": {"title": "WhatsApp", "hwnd": 1},
            "vision_scope": "foreground",
            "uia_actionable": False,
            "elements": [],
        },
        "error": None,
    }


def test_v3520_store_persists_only_bounded_route_statistics(tmp_path):
    path = tmp_path / "route-performance.json"
    store = RecoveryRoutePerformanceStore(path)
    store.record("foreground_vision", success=True)
    store.record("foreground_vision", success=False)
    store.record("not_a_real_route", success=True)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == "3.6.0"
    assert set(raw["routes"]) == {"foreground_vision"}
    assert "goal" not in json.dumps(raw).lower()
    assert "target" not in json.dumps(raw).lower()

    reloaded = RecoveryRoutePerformanceStore(path).snapshot()
    assert reloaded["foreground_vision"]["effective_samples"] == 2.0
    assert 0.0 < reloaded["foreground_vision"]["success_rate"] < 1.0


def test_v3520_old_learning_decays_by_half_life(tmp_path):
    clock = Clock(1000.0)
    store = RecoveryRoutePerformanceStore(
        tmp_path / "decay.json",
        half_life_seconds=100.0,
        clock=clock,
    )
    store.record("uia_reground", success=True)
    before = store.snapshot()["uia_reground"]["success_weight"]
    clock.value += 100.0
    after = store.snapshot()["uia_reground"]["success_weight"]
    assert before == 1.0
    assert 0.49 <= after <= 0.51


def test_v3520_learning_weight_is_capped(tmp_path):
    store = RecoveryRoutePerformanceStore(
        tmp_path / "cap.json",
        max_effective_weight=8.0,
    )
    for _ in range(30):
        store.record("desktop_vision", success=True)
    prior = store.snapshot()["desktop_vision"]
    assert prior["effective_samples"] <= 8.000001


def test_v3520_tracker_learns_only_after_semantic_verification(tmp_path):
    store = RecoveryRoutePerformanceStore(tmp_path / "tracker.json")
    tracker = TaskTracker("Find Darkness", recovery_performance_store=store)
    tracker.record_automatic_recovery(_directive(), _recovery_payload())
    assert store.snapshot() == {}

    tracker.record(
        "device_computer_verify",
        {"condition": "text_contains", "target": "Darkness"},
        {
            "ok": True,
            "output": {
                "status": "PASS",
                "semantic_goal_verified": True,
                "decision": {
                    "action": "ACCEPT",
                    "goal_sufficient": True,
                    "failure_count": 0,
                    "retry_budget_remaining": 2,
                },
            },
            "error": None,
        },
    )
    prior = store.snapshot()["foreground_vision"]
    assert prior["success_weight"] == 1.0
    assert tracker.recovery_learning_pending_route == ""


def test_v3520_tracker_records_failed_semantic_outcome_for_pending_route(tmp_path):
    store = RecoveryRoutePerformanceStore(tmp_path / "tracker-fail.json")
    tracker = TaskTracker("Find Darkness", recovery_performance_store=store)
    tracker.record_automatic_recovery(_directive("uia_reground"), _recovery_payload())
    tracker.record(
        "device_computer_verify",
        {"condition": "text_contains", "target": "Darkness"},
        {
            "ok": True,
            "output": {
                "status": "FAIL",
                "semantic_goal_verified": False,
                "decision": {
                    "action": "RETRY",
                    "goal_sufficient": False,
                    "failure_count": 1,
                    "retry_budget_remaining": 1,
                },
            },
            "error": None,
        },
    )
    assert store.snapshot()["uia_reground"]["failure_weight"] == 1.0


def test_v3520_tracker_exposes_persistent_priors_to_planner(tmp_path):
    store = RecoveryRoutePerformanceStore(tmp_path / "planner.json")
    store.record("desktop_vision", success=True)
    tracker = TaskTracker("Find Darkness", recovery_performance_store=store)
    constraints = tracker.recovery_planner_constraints()
    assert constraints["learned_route_priors_version"] == "3.6.0"
    assert "desktop_vision" in constraints["learned_route_priors"]
    assert constraints["action_replay_allowed"] is False


def test_v3520_adaptive_scorer_uses_bounded_persistent_prior_without_overriding_live_safety():
    output = _verification_output()
    args = {"scope": "foreground", "condition": "text_contains"}
    preferred = select_recovery_route(output, args)
    baseline = rank_recovery_routes(output, args, {}, preferred_route=preferred)
    learned = rank_recovery_routes(
        output,
        args,
        {
            "learned_route_priors": {
                "uia_reground": {
                    "success_rate": 0.95,
                    "effective_samples": 20.0,
                },
                "foreground_vision": {
                    "success_rate": 0.05,
                    "effective_samples": 20.0,
                },
            }
        },
        preferred_route=preferred,
    )
    base_scores = {x["route"]: x["score"] for x in baseline["rankings"]}
    learned_scores = {x["route"]: x["score"] for x in learned["rankings"]}
    assert 0 < learned_scores["uia_reground"] - base_scores["uia_reground"] <= 12
    assert -12 <= learned_scores["foreground_vision"] - base_scores["foreground_vision"] < 0
    assert learned["persistent_learning_version"] == "3.6.0"
    assert learned["selected_route"] == "uia_reground"
    assert learned["action_replay_allowed"] is False

    exhausted = rank_recovery_routes(
        output,
        args,
        {
            "exhausted_routes": ["uia_reground"],
            "learned_route_priors": {
                "uia_reground": {"success_rate": 1.0, "effective_samples": 32.0}
            },
        },
        preferred_route=preferred,
    )
    assert "uia_reground" not in {x["route"] for x in exhausted["rankings"]}


def test_v3520_learning_message_states_advisory_no_replay_contract():
    message = learned_route_prior_message(
        {"foreground_vision": {"success_rate": 0.8, "effective_samples": 4}}
    )
    assert "v3.6.0" in message
    assert "bounded and decay" in message
    assert "never grant action replay" in message
