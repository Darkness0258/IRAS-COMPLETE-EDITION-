from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from iras.device_bridge.executor import DeviceExecutor
from iras.models import PermissionLevel
from iras.providers.multi_provider import MultiProvider, ProviderSlot
from iras.remote_access import action_permission


class _ProbeProvider:
    def __init__(self, model: str = "probe/model", *, state: str = "online"):
        self.model = model
        self.state = state
        self.last_request_ms = 0
        self.last_first_token_ms = 0

    def probe(self, timeout: float = 6.0):
        if self.state == "error":
            raise RuntimeError("LLM HTTP 429: rate limit reached")
        return {
            "ok": self.state == "online",
            "verified": self.state == "online",
            "state": self.state,
            "latency_ms": 17,
            "status_code": 200 if self.state == "online" else 404,
        }

    def complete(self, messages, tools):
        self.last_request_ms = 23
        return {"ok": True}

    def stream_text(self, messages, tools):
        yield "ok"


def test_provider_is_configured_until_actively_verified():
    pool = MultiProvider([ProviderSlot("final-configured", _ProbeProvider())])
    row = pool.diagnostics()[0]
    assert row["state"] == "configured"
    assert row["ready"] is False
    assert row["routable"] is True

    rows = pool.probe_all()
    assert rows[0]["state"] == "online"
    assert rows[0]["ready"] is True
    assert rows[0]["last_probe_at"] is not None
    assert rows[0]["latency_ms"] == 17


def test_provider_probe_rate_limit_updates_routing_state():
    pool = MultiProvider([ProviderSlot("final-rate-limit", _ProbeProvider(state="error"))], cooldown_seconds=30)
    row = pool.probe_all()[0]
    assert row["state"] == "rate_limited"
    assert row["ready"] is False
    assert row["routable"] is False
    assert row["cooldown_seconds"] > 0


def test_provider_health_is_shared_across_worker_pools():
    name = "shared-final-health"
    first = MultiProvider([ProviderSlot(name, _ProbeProvider("shared/model"))])
    first.complete([], [])
    second = MultiProvider([ProviderSlot(name, _ProbeProvider("shared/model"))])
    row = second.diagnostics()[0]
    assert row["attempts"] >= 1
    assert row["successes"] >= 1
    assert row["last_success_at"] is not None


def test_health_aware_routing_can_demote_degraded_primary():
    primary = ProviderSlot("final-primary", _ProbeProvider("primary/model"))
    backup = ProviderSlot("final-backup", _ProbeProvider("backup/model"))
    pool = MultiProvider([primary, backup])
    # A verified degraded probe should affect route ranking without fabricating
    # a successful request.
    pool._mark_probe(primary, {"ok": False, "state": "offline", "latency_ms": 5, "status_code": 503})
    order = pool.route_order()
    assert order[0] == "final-backup"


def _git(*args: str, cwd: Path):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def test_guarded_git_rollback_restores_tracked_and_preserves_untracked(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", cwd=repo)
    _git("config", "user.email", "iras@example.invalid", cwd=repo)
    _git("config", "user.name", "IRAS Test", cwd=repo)
    tracked = repo / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    _git("add", "tracked.txt", cwd=repo)
    _git("commit", "-m", "baseline", cwd=repo)

    executor = DeviceExecutor.__new__(DeviceExecutor)
    executor.allowed_roots = [tmp_path.resolve()]
    head = executor.git_head(str(repo))["head"]

    tracked.write_text("after\n", encoding="utf-8")
    untracked = repo / "new.txt"
    untracked.write_text("keep me\n", encoding="utf-8")

    result = executor.git_restore_checkpoint(str(repo), head, baseline_clean=True)
    assert result["restored"] is True
    assert tracked.read_text(encoding="utf-8") == "before\n"
    assert untracked.exists()
    assert "new.txt" in result["untracked_preserved"]


def test_guarded_git_rollback_refuses_dirty_baseline(tmp_path: Path):
    executor = DeviceExecutor.__new__(DeviceExecutor)
    executor.allowed_roots = [tmp_path.resolve()]
    with pytest.raises(PermissionError, match="did not start from a clean"):
        executor.git_restore_checkpoint(str(tmp_path), "a" * 40, baseline_clean=False)


def test_rollback_is_critical_and_git_head_is_read_only():
    assert action_permission("git_head", {}) == PermissionLevel.READ
    assert action_permission("git_restore_checkpoint", {}) == PermissionLevel.CRITICAL


def test_final_web_and_cloud_contracts_are_present():
    web = Path("clients/web/index.html").read_text(encoding="utf-8")
    cloud = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    orchestration = Path("src/iras/orchestration.py").read_text(encoding="utf-8")
    assert 'id="rollbackGoal"' in web
    assert '/v1/providers/status?probe=true' in web
    assert '/rollback' in web
    assert '@app.post("/v1/orchestration/runs/{run_id}/rollback")' in cloud
    assert 'database_url=settings.database_url' in cloud
    assert 'iras_orchestration_journal' in orchestration
    assert '"version": 3' in orchestration


def test_final_ci_targets_current_v44_validator():
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert r".\run-v500-validation.ps1" in text
    assert "run-v430-validation.ps1" not in text
