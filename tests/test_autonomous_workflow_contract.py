from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return (
        ROOT
        / path
    ).read_text(
        encoding="utf-8"
    )


def test_agent_uses_workflow_tracker():
    text = _read(
        Path(
            "src/iras/core/agent.py"
        )
    )

    assert "TaskTracker" in text
    assert "planner_step_budget" in text
    assert "workflow_system_nudge" in text
    assert "task_tracker.before_call(" in text
    assert "task_tracker.record(" in text
    assert "task_tracker" in text
    assert "after_result_nudge(" in text
    assert "finalization_nudge" in text


def test_agent_blocks_identical_failed_retries():
    text = _read(
        Path(
            "src/iras/core/agent.py"
        )
    )

    assert (
        '"workflow_repeat_blocked"'
        in text
    )


def test_agent_audits_workflow_completion():
    text = _read(
        Path(
            "src/iras/core/agent.py"
        )
    )

    assert (
        '"autonomous_workflow_finished"'
        in text
    )
    assert (
        '"workflow_mode": planner_mode'
        in text
    )
    assert (
        '"step_budget": step_budget'
        in text
    )


def test_workflow_mode_keeps_normal_agent_default_unchanged():
    text = _read(
        Path(
            "src/iras/core/agent.py"
        )
    )

    assert "max_steps=8" in text
    assert "if planner_mode" in text
    assert "else self.max_steps" in text


def test_workflow_engine_does_not_add_unrestricted_execution():
    text = _read(
        Path(
            "src/iras/device_bridge/task_engine.py"
        )
    )

    forbidden = (
        "run_shell",
        "powershell.exe",
        "cmd.exe",
        "subprocess.Popen",
        "os.system",
    )

    for item in forbidden:
        assert item not in text
