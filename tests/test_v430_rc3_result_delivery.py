from __future__ import annotations

from pathlib import Path

import pytest

from iras.device_bridge.remote_context import (
    current_remote_command_context,
    remote_command_context,
)
from iras.device_bridge.tools import _bind_project_arguments
from iras.orchestration import OrchestrationManager


def test_verified_project_root_binds_relative_agent_paths():
    root = r"D:\Projects\IRAS-complete"
    assert _bind_project_arguments("git_status", {"repo": "."}, root)["repo"] == root
    assert _bind_project_arguments("git_diff", {"repo": "IRAS"}, root)["repo"] == root
    bound = _bind_project_arguments(
        "read_text",
        {"path": r"src\iras\cloud_api.py"},
        root,
    )
    assert bound["path"] == r"D:\Projects\IRAS-complete\src\iras\cloud_api.py"


def test_verified_project_root_rejects_absolute_escape():
    with pytest.raises(PermissionError):
        _bind_project_arguments(
            "read_text",
            {"path": r"C:\Windows\System32\drivers\etc\hosts"},
            r"D:\Projects\IRAS-complete",
        )


def test_remote_context_carries_verified_project_root():
    with remote_command_context(
        {"session_id": "s", "requester_device": "web", "device_id": "pc"},
        project_root=r"D:\Projects\IRAS-complete",
    ):
        ctx = current_remote_command_context()
        assert ctx.project_root == r"D:\Projects\IRAS-complete"
        assert ctx.device_id == "pc"


def _run_with_coordinator_result(tmp_path: Path, coordinator_result: str):
    def runner(prompt, context):
        if context.get("agent_role") == "coordinator":
            return {"result": coordinator_result, "metrics": {}}
        return {"result": "work completed", "metrics": {}}

    manager = OrchestrationManager(
        runner,
        max_workers=2,
        journal_path=tmp_path / "runs.json",
    )
    try:
        run = manager.submit_graph(
            "Improve one thing",
            [
                {
                    "id": "work",
                    "title": "Work",
                    "prompt": "Do the work",
                    "role": "coder",
                    "priority": 80,
                }
            ],
            add_coordinator=True,
        )
        return manager.wait(run["run_id"], timeout=5)
    finally:
        manager.close()


def test_coordinator_incomplete_downgrades_terminal_run_state(tmp_path):
    run = _run_with_coordinator_result(
        tmp_path,
        "OUTCOME: INCOMPLETE\nThe requested change was not verified.",
    )
    assert run["verified_outcome"] == "incomplete"
    assert run["state"] == "partial_failure"


def test_coordinator_complete_keeps_success_state(tmp_path):
    run = _run_with_coordinator_result(
        tmp_path,
        "OUTCOME: COMPLETE\nThe objective completed and was verified.",
    )
    assert run["verified_outcome"] == "complete"
    assert run["state"] == "succeeded"


def test_web_chat_watches_background_orchestration_result():
    web = Path("clients/web/index.html").read_text(encoding="utf-8")
    assert "async function watchAgentRunInChat(runId)" in web
    assert "watchAgentRunInChat(activeGoalRunId);" in web
    assert "announceAgentRun(run)" in web
    assert "verified outcome" in web
