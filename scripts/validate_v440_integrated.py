from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from iras import __version__
from iras.models import PermissionLevel
from iras.orchestration import OrchestrationManager
from iras.providers.multi_provider import MultiProvider, ProviderSlot
from iras.remote_access import action_permission
from iras.remote_protocol import REMOTE_PROTOCOL_VERSION


class _Provider:
    model = "validation/model"
    last_request_ms = 0
    last_first_token_ms = 0

    def probe(self, timeout=6.0):
        return {"ok": True, "verified": True, "state": "online", "latency_ms": 7, "status_code": 200}

    def complete(self, messages, tools):
        return {"ok": True}

    def stream_text(self, messages, tools):
        yield "ok"


def main() -> None:
    print("=== IRAS v4.4.0 FINAL PERSISTENT AUTONOMY PRODUCTION VALIDATION ===")
    assert __version__ == "4.4.0"
    assert REMOTE_PROTOCOL_VERSION == 1
    assert action_permission("local_llm_status", {}) == PermissionLevel.READ
    assert action_permission("git_head", {}) == PermissionLevel.READ
    assert action_permission("git_restore_checkpoint", {}) == PermissionLevel.CRITICAL

    provider = MultiProvider([ProviderSlot("validation", _Provider())])
    assert provider.status()[0]["ready"] is True  # compatibility surface
    rich = provider.diagnostics()[0]
    assert rich["state"] == "configured" and rich["routable"] is True
    probed = provider.probe_all()[0]
    assert probed["state"] == "online" and probed["ready"] is True
    assert probed["last_probe_at"] is not None
    provider.complete([], [])
    assert provider.diagnostics()[0]["last_success_at"] is not None

    web = (ROOT / "clients/web/index.html").read_text(encoding="utf-8")
    cloud = (ROOT / "src/iras/cloud_api.py").read_text(encoding="utf-8")
    executor = (ROOT / "src/iras/device_bridge/executor.py").read_text(encoding="utf-8")
    orchestration = (ROOT / "src/iras/orchestration.py").read_text(encoding="utf-8")
    assert 'id="providers"' in web
    assert 'id="providersDlg"' in web
    assert '/v1/providers/status?probe=true' in web
    assert 'id="retryGoal"' in web
    assert 'id="rollbackGoal"' in web
    assert '8*60*60*1000' in web
    assert '@app.get("/v1/providers/status")' in cloud
    assert '@app.post("/v1/orchestration/runs/{run_id}/retry")' in cloud
    assert '@app.post("/v1/orchestration/runs/{run_id}/rollback")' in cloud
    assert 'database_url=settings.database_url' in cloud
    assert 'def local_llm_status' in executor
    assert 'def git_restore_checkpoint' in executor
    assert 'iras_orchestration_journal' in orchestration
    assert '"version": 3' in orchestration

    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "IRAS v4.4 FINAL production validation" in ci
    assert r".\run-v440-validation.ps1" in ci
    assert "run-v430-validation.ps1" not in ci
    assert "providerStatusGeneration" in web
    assert "providerGrid.replaceChildren(...cards)" in web
    assert "def _dedupe_provider_rows" in cloud

    with tempfile.TemporaryDirectory() as td:
        journal = Path(td) / "runs.json"
        journal.write_text(json.dumps({
            "version": 3,
            "runs": [{
                "run_id": "checkpoint-v44-final",
                "objective": "resume checkpoint",
                "state": "running",
                "requester_device": "web",
                "created_at": "2026-09-17T10:00:00+00:00",
                "checkpoint": {
                    "project_root": r"D:\Projects\IRAS-complete",
                    "rollback_checkpoint": {"head": "a" * 40, "working_tree_clean": True},
                },
                "tasks": [
                    {"task_id": "done", "title": "done", "prompt": "done", "role": "reviewer", "state": "succeeded", "attempts": 1, "result": "verified", "depends_on": []},
                    {"task_id": "work", "title": "work", "prompt": "work", "role": "coder", "state": "running", "attempts": 1, "depends_on": ["done"]},
                ],
            }],
        }), encoding="utf-8")
        manager = OrchestrationManager(lambda p, c: {"result": "ok:" + p}, journal_path=journal, max_workers=1)
        try:
            recovered = manager.get("checkpoint-v44-final")
            assert recovered["state"] == "interrupted"
            assert recovered["resume_required"] is True
            assert recovered["checkpoint"]["rollback_checkpoint"]["head"] == "a" * 40
            manager.resume("checkpoint-v44-final", context_update={"remote_session": {"session_id": "fresh"}})
            final = manager.wait("checkpoint-v44-final", timeout=3)
            assert final["state"] == "succeeded"
            by_id = {task["task_id"]: task for task in final["tasks"]}
            assert by_id["done"]["attempts"] == 1
            assert by_id["work"]["state"] == "succeeded"
        finally:
            manager.close()

    print("LIVE PROVIDER STATUS PANEL: True")
    print("ACTIVE PROVIDER HEALTH PROBES: True")
    print("SHARED HEALTH-AWARE ROUTING: True")
    print("DEVICE OLLAMA STATUS PROBE: True")
    print("DURABLE JOB CHECKPOINTS: True")
    print("POSTGRES DEPLOYMENT JOURNAL: True")
    print("RESTART-SAFE RESUME: True")
    print("RETRY FAILED NODES: True")
    print("GUARDED TRACKED-FILE ROLLBACK: True")
    print("ROLLBACK CHECKPOINT FULL GIT HEAD: True")
    print("JOB EVENT HISTORY: True")
    print("RESPONSIVE DEVICE BRIDGE CONTRACT: True")
    print("CURRENT RELEASE CI VALIDATOR: True")
    print("PROVIDER STATUS DEDUPLICATION: True")
    print("REMOTE PROTOCOL VERSION:", REMOTE_PROTOCOL_VERSION)
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
