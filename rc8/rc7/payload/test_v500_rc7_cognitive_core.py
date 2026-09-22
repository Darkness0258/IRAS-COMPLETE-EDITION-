from __future__ import annotations

import time

from iras.v5.common import EventBus, SQLiteDB
from iras.v5.cognitive_core import CognitiveCore, FuzzyLogicEngine, HybridReasoner


def _core(tmp_path):
    return CognitiveCore(SQLiteDB(tmp_path / "cognition.db"), EventBus())


def test_rc7_fuzzy_willingness_is_graded():
    fuzzy = FuzzyLogicEngine()
    low = fuzzy.willingness(confidence=.3, utility=.4, urgency=.2, risk=.8)
    high = fuzzy.willingness(confidence=.9, utility=.9, urgency=.8, risk=.1)
    assert 0 <= low < high <= 1


def test_rc7_inductive_and_deductive_reasoning():
    reasoner = HybridReasoner()
    deductions = reasoner.deduct(
        {"tests_pass": .95, "review_ok": .9},
        [{"if": {"tests_pass": .8, "review_ok": .8}, "then": "release_candidate", "weight": .95}],
    )
    assert deductions and deductions[0]["conclusion"] == "release_candidate"
    inductions = reasoner.induce([
        {"features": {"gpu_old": 1}, "outcome": "use_cpu"},
        {"features": {"gpu_old": 1}, "outcome": "use_cpu"},
        {"features": {"gpu_new": 1}, "outcome": "use_gpu"},
    ])
    assert any(x["feature"] == "gpu_old" and x["outcome"] == "use_cpu" for x in inductions)


def test_rc7_neural_associative_memory_learns_from_feedback(tmp_path):
    core = _core(tmp_path)
    first = core.remember(
        "Spotify playback verification uses visual pause state and query evidence",
        importance=.8,
    )
    core.remember(
        "Visual verification uses OmniParser evidence on the current screen",
        importance=.7,
    )
    recalled = core.recall("spotify visual verification", limit=5, hops=2)
    assert recalled and any(x["memory_id"] == first["memory_id"] for x in recalled)
    before = next(x for x in recalled if x["memory_id"] == first["memory_id"])["confidence"]
    learned = core.reinforce(first["memory_id"], .8, note="successful verification")
    assert learned["confidence"] >= before
    status = core.status()
    assert status["concept_neurons"] > 0
    assert status["synapses"] > 0


def test_rc7_self_directed_intention_uses_goals_and_fuzzy_drive(tmp_path):
    core = _core(tmp_path)
    core.bind_goal_provider(lambda: [{"item_id": "g1", "title": "Finish IRAS RC7", "progress": .4}])
    tick = core.tick()
    assert tick["created_intentions"]
    intention = tick["created_intentions"][0]
    assert intention["status"] == "proposed"
    assert intention["willingness"] >= .55


def test_rc7_continuous_background_cognition(tmp_path):
    core = _core(tmp_path)
    core.bind_goal_provider(lambda: [])
    for index in range(5):
        core.remember(f"learning experience {index} about automation", importance=.5)
    core.start(interval_seconds=2)
    try:
        deadline = time.time() + 4.5
        while time.time() < deadline and core.status()["last_tick"] is None:
            time.sleep(.05)
        status = core.status()
        assert status["running"] is True
        assert status["last_tick"] is not None
        assert core.intentions(status="proposed")
    finally:
        core.stop()


def test_rc7_memory_has_no_application_item_count_cap(tmp_path):
    core = _core(tmp_path)
    for index in range(180):
        core.remember(f"unbounded memory sample {index} concept_{index}", importance=.4)
    status = core.status()
    assert status["memory_items"] == 180
    assert status["memory_policy"] == "no_application_item_cap_storage_bounded"


def test_rc7_biological_signal_reference_without_software_slowdown(tmp_path):
    status = _core(tmp_path).status()
    assert 50 <= status["biological_reference_signal_speed_mps"] <= 100
    assert "not artificially delayed" in status["actual_signal_transport"]
