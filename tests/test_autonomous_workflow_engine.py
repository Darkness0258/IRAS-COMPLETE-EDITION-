from iras.device_bridge.task_engine import (
    TaskTracker,
    planner_step_budget,
)


def test_planner_gets_bounded_larger_step_budget():
    assert planner_step_budget(8) == 12
    assert planner_step_budget(12) == 12
    assert planner_step_budget(20) == 16


def test_repeated_failed_call_is_blocked_on_third_identical_attempt():
    tracker = TaskTracker(
        "open an app"
    )

    args = {
        "app": "Example",
    }

    allowed, _ = tracker.before_call(
        "device_open_app",
        args,
    )
    assert allowed is True

    tracker.record(
        "device_open_app",
        args,
        {
            "ok": False,
            "output": None,
            "error": "failed",
        },
    )

    allowed, _ = tracker.before_call(
        "device_open_app",
        args,
    )
    assert allowed is True

    tracker.record(
        "device_open_app",
        args,
        {
            "ok": False,
            "output": None,
            "error": "failed again",
        },
    )

    allowed, reason = tracker.before_call(
        "device_open_app",
        args,
    )

    assert allowed is False
    assert "different safe approach" in reason


def test_interaction_requires_verification():
    tracker = TaskTracker(
        "type into app"
    )

    tracker.record(
        "device_interact_app",
        {
            "app": "Notepad",
        },
        {
            "ok": True,
            "output": {
                "command_sent": True,
            },
            "error": None,
        },
    )

    assert (
        tracker.needs_verification
        is True
    )

    assert (
        "not verified"
        in tracker
        .finalization_nudge()
    )


def test_observation_clears_pending_verification():
    tracker = TaskTracker(
        "type then inspect"
    )

    tracker.record(
        "device_interact_app",
        {
            "app": "Notepad",
        },
        {
            "ok": True,
            "output": {
                "command_sent": True,
            },
            "error": None,
        },
    )

    tracker.record(
        "device_observe_ui",
        {
            "app": "Notepad",
        },
        {
            "ok": True,
            "output": {
                "elements": [],
            },
            "error": None,
        },
    )

    assert (
        tracker.needs_verification
        is False
    )

    assert (
        tracker.finalization_nudge()
        == ""
    )


def test_semantic_action_with_reobservation_counts_as_verified():
    tracker = TaskTracker(
        "click settings"
    )

    tracker.record(
        "device_semantic_action",
        {
            "app": "Discord",
            "action": "click",
            "target": "Settings",
        },
        {
            "ok": True,
            "output": {
                "verification_observation": {
                    "window_name": "Discord",
                },
            },
            "error": None,
        },
    )

    assert (
        tracker.needs_verification
        is False
    )


def test_three_failures_trigger_recovery_guidance():
    tracker = TaskTracker(
        "complete workflow"
    )

    for index in range(3):
        name = (
            "device_open_app"
            + str(index)
        )

        tracker.record(
            name,
            {},
            {
                "ok": False,
                "output": None,
                "error": "failure",
            },
        )

    nudge = tracker.after_result_nudge(
        {
            "ok": False,
        }
    )

    assert (
        "three consecutive"
        in nudge.lower()
    )
