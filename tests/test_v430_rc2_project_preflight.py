from __future__ import annotations

import subprocess
from pathlib import Path

from iras.device_bridge.executor import DeviceExecutor
from iras.device_bridge.tools import make_tools
from iras.execution_router import needs_project_workspace
from iras.models import PermissionLevel
from iras.orchestration import OrchestrationManager
from iras.remote_access import action_permission


class _DummyStore:
    def request_and_wait(self, **kwargs):
        return kwargs

    def list_devices(self):
        return []


def _git_repo(path: Path, name: str = "repo") -> Path:
    repo = path / name
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "pyproject.toml").write_text("[project]\nname='sample'\nversion='0'\n", encoding="utf-8")
    return repo


def test_find_projects_resolves_named_repo_inside_allowed_roots(tmp_path):
    root = tmp_path / "Projects"
    root.mkdir()
    _git_repo(root, "OtherApp")
    target = _git_repo(root, "IRAS-complete")

    executor = DeviceExecutor([str(root)])
    result = executor.find_projects("IRAS", max_depth=2)

    assert result["projects"]
    assert Path(result["projects"][0]["path"]) == target.resolve()
    assert result["projects"][0]["query_match"] is True
    assert str(root.resolve()) in result["allowed_roots"]


def test_find_projects_never_crosses_bridge_roots_or_symlinks(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = _git_repo(outside, "IRAS-secret")
    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        link = None

    executor = DeviceExecutor([str(root)])
    result = executor.find_projects("IRAS", max_depth=4)
    returned = {Path(item["path"]).resolve() for item in result["projects"]}
    assert target.resolve() not in returned


def test_find_projects_is_read_only_and_exposed_to_agent_tools():
    assert action_permission("find_projects", {}) == PermissionLevel.READ
    tools = {tool.name: tool for tool in make_tools(_DummyStore())}
    assert "device_find_projects" in tools
    assert tools["device_find_projects"].required_permission({"query": "IRAS"}) == PermissionLevel.READ


def test_project_workspace_detection_catches_engineering_requests_but_not_chat():
    assert needs_project_workspace(
        "Inspect the IRAS project, implement one safe fix, run tests, and review the diff"
    )
    assert not needs_project_workspace("Open Spotify and play naat")


def test_orchestration_waits_for_temporary_device_outage_without_spending_retry_budget(tmp_path):
    attempts = {"count": 0}

    def runner(_prompt, _context):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("IRAS device 'Validation PC' is offline.")
        return {"result": "device recovered", "metrics": {}}

    manager = OrchestrationManager(
        runner,
        max_workers=1,
        max_tasks_per_run=4,
        provider_wait_budget_seconds=0,
        device_wait_budget_seconds=1,
        journal_path=tmp_path / "runs.json",
    )
    try:
        run = manager.submit_graph(
            "temporary device outage",
            [{"id": "device", "prompt": "check device", "max_retries": 0}],
            add_coordinator=False,
        )
        final = manager.wait(run["run_id"], timeout=3)
        assert final["state"] == "succeeded"
        task = final["tasks"][0]
        assert task["device_waits"] == 1
        assert task["attempts"] == 1
        assert attempts["count"] == 2
    finally:
        manager.close()


def test_cloud_worker_contract_injects_resolved_windows_project_root():
    source = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    assert "Resolved Windows project root:" in source
    assert "_prepare_orchestration_context" in source
    assert '"find_projects"' in source
    assert "project_root" in source
