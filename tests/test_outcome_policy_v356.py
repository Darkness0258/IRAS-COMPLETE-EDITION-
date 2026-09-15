from iras.device_bridge.outcome_policy import (
    ACCEPT,
    ESCALATE_VISION,
    RECOVER,
    RETRY,
    decide_outcome,
)
from iras.device_bridge.task_engine import TaskTracker


def _assessment(
    *,
    verified=False,
    semantic=False,
    state_only=False,
    outcome_class="semantic_goal",
    confidence=0.98,
    sources=None,
    reasons=None,
    state_changed=False,
):
    return {
        "condition_verified": verified,
        "semantic_goal_verified": semantic,
        "state_only_verified": state_only,
        "outcome_class": outcome_class,
        "confidence": confidence,
        "evidence_sources": sources or [],
        "reason_codes": reasons or [],
        "state_delta": {
            "available": True,
            "screen_changed": state_changed,
            "visual_changed": state_changed,
            "foreground_changed": False,
        },
    }


def test_semantic_target_miss_requests_vision_before_retry():
    decision = decide_outcome(
        _assessment(verified=False, sources=["uia"]),
        condition="text_contains",
        vision_escalated=False,
        can_escalate_vision=True,
        failure_count=0,
    )

    assert decision["action"] == ESCALATE_VISION
    assert decision["goal_sufficient"] is False
    assert "semantic_target_needs_visual_confirmation" in decision["reason_codes"]


def test_verified_semantic_goal_is_accepted_as_goal_sufficient():
    decision = decide_outcome(
        _assessment(
            verified=True,
            semantic=True,
            sources=["uia", "vision"],
        ),
        condition="text_contains",
        vision_escalated=True,
        can_escalate_vision=False,
        failure_count=0,
    )

    assert decision["action"] == ACCEPT
    assert decision["condition_accepted"] is True
    assert decision["goal_sufficient"] is True


def test_state_only_pass_is_accepted_but_not_goal_sufficient():
    decision = decide_outcome(
        _assessment(
            verified=True,
            state_only=True,
            outcome_class="state_transition",
            confidence=0.90,
            sources=["screenshot_hash"],
        ),
        condition="screen_changed",
        vision_escalated=False,
        can_escalate_vision=False,
        failure_count=0,
    )

    assert decision["action"] == ACCEPT
    assert decision["condition_accepted"] is True
    assert decision["goal_sufficient"] is False
    assert "state_only_evidence_not_goal_completion" in decision["reason_codes"]


def test_failed_goal_uses_bounded_retry_budget():
    decision = decide_outcome(
        _assessment(verified=False, sources=["vision"], state_changed=True),
        condition="text_contains",
        vision_escalated=True,
        can_escalate_vision=False,
        failure_count=1,
        max_retries=2,
    )

    assert decision["action"] == RETRY
    assert decision["retry_budget_remaining"] == 2
    assert "state_changed_without_verified_goal" in decision["reason_codes"]


def test_exhausted_retry_budget_requires_recovery():
    decision = decide_outcome(
        _assessment(verified=False, sources=["vision"]),
        condition="text_contains",
        vision_escalated=True,
        can_escalate_vision=False,
        failure_count=3,
        max_retries=2,
    )

    assert decision["action"] == RECOVER
    assert decision["retry_budget_remaining"] == 0
    assert "retry_budget_exhausted" in decision["reason_codes"]


def test_task_tracker_honors_outcome_policy_decisions():
    tracker = TaskTracker("Search for Metallica")

    tracker.record(
        "device_computer_verify",
        {"condition": "text_contains", "target": "Metallica"},
        {
            "ok": True,
            "output": {
                "status": "FAIL",
                "decision": {
                    "action": "RETRY",
                    "failure_count": 1,
                    "retry_budget_remaining": 2,
                    "goal_sufficient": False,
                },
            },
        },
    )

    assert tracker.needs_verification is True
    assert tracker.last_outcome_decision == "RETRY"
    assert tracker.outcome_retry_budget_remaining == 2
    assert "OUTCOME RETRY" in tracker.after_result_nudge({"ok": True})

    tracker.record(
        "device_computer_verify",
        {"condition": "text_contains", "target": "Metallica"},
        {
            "ok": True,
            "output": {
                "status": "FAIL",
                "decision": {
                    "action": "RECOVER",
                    "failure_count": 3,
                    "retry_budget_remaining": 0,
                    "goal_sufficient": False,
                },
            },
        },
    )

    assert tracker.outcome_recovery_required is True
    assert "re-plan" in tracker.finalization_nudge().lower()
