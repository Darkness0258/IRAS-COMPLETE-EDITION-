from iras.v5.common import EventBus, SQLiteDB
from iras.v5.continuity import GoalContinuityEngine


def _engine(tmp_path):
    return GoalContinuityEngine(SQLiteDB(tmp_path / "state.db"), EventBus())


def test_begin_is_persistent_and_run_key_is_idempotent(tmp_path):
    engine = _engine(tmp_path)
    first = engine.begin("Finish the current authorized task", run_key="goal-1")
    restarted = _engine(tmp_path)
    second = restarted.begin("Finish the current authorized task", run_key="goal-1")
    assert first["run_id"] == second["run_id"]
    assert first["phase"] == "observe"
    assert engine.status()["side_effect_replay_allowed"] is False


def test_action_requires_verification(tmp_path):
    engine = _engine(tmp_path)
    run = engine.begin("Open the requested app")
    engine.record(run["run_id"], "observe", "App is visible", world_fingerprint="screen:a")
    engine.record(run["run_id"], "action", "Clicked the requested control", reversible=True)
    assessment = engine.assess(run["run_id"], world_fingerprint="screen:a")
    assert assessment["decision"] == "verify"
    assert assessment["permission_bypass_allowed"] is False


def test_failed_verification_routes_to_repair(tmp_path):
    engine = _engine(tmp_path)
    run = engine.begin("Reach the requested end state")
    engine.record(run["run_id"], "observe", "Fresh state", world_fingerprint="screen:a")
    engine.record(run["run_id"], "verification", "Expected result is not visible", payload={"verified": False})
    assessment = engine.assess(run["run_id"], world_fingerprint="screen:a")
    assert assessment["decision"] == "repair"


def test_world_change_forces_reobserve_before_continuing(tmp_path):
    engine = _engine(tmp_path)
    run = engine.begin("Continue across an interruption")
    engine.record(run["run_id"], "observe", "Observed original state", world_fingerprint="screen:a")
    assessment = engine.assess(run["run_id"], world_fingerprint="screen:b")
    assert assessment["decision"] == "reobserve"
    assert assessment["world_changed"] is True


def test_terminal_runs_stop_and_do_not_accept_more_events(tmp_path):
    engine = _engine(tmp_path)
    run = engine.begin("Complete and stop")
    engine.record(run["run_id"], "completion", "End state independently verified", payload={"verified": True})
    assessment = engine.assess(run["run_id"])
    assert assessment["decision"] == "stop"
    assert assessment["status"] == "completed"
    try:
        engine.record(run["run_id"], "action", "Should not run")
    except ValueError as exc:
        assert "terminal" in str(exc)
    else:
        raise AssertionError("terminal continuity run accepted another action")


def test_secret_like_payload_fields_are_redacted(tmp_path):
    engine = _engine(tmp_path)
    run = engine.begin("Keep evidence without storing credentials", metadata={"api_key": "abc", "safe": "ok"})
    saved = engine.record(
        run["run_id"],
        "observe",
        "Observed authenticated state",
        payload={"authorization": "Bearer secret", "nested": {"password": "hidden", "value": 3}},
        world_fingerprint="screen:a",
    )
    assert saved["metadata"]["api_key"] == "[redacted]"
    assert saved["metadata"]["safe"] == "ok"
    event = saved["events"][-1]
    assert event["payload"]["authorization"] == "[redacted]"
    assert event["payload"]["nested"]["password"] == "[redacted]"
    assert event["payload"]["nested"]["value"] == 3
