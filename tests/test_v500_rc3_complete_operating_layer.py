from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import time
from pathlib import Path

from iras.v5.runtime import V5Runtime
from iras.v5.encrypted_sync import EncryptedSync
from iras.v5.visual_agent import AdvancedVisualAgent
from iras.v5.voice_runtime import FullDuplexVoiceRuntime


def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_VAULT_MASTER_KEY", EncryptedSync.new_key())
    return V5Runtime(tmp_path)


def test_rc3_scheduler_pause_resume_and_offline_execution(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch)
    job = rt.scheduler.add(name="brief", prompt="status", interval_seconds=60)
    assert rt.scheduler.pause(job["job_id"])["paused"] is True
    assert rt.scheduler.resume(job["job_id"])["paused"] is False
    rows = rt.scheduler.run_due(lambda prompt, row: "ok")
    assert rows and rows[0]["ok"] is True


def test_rc3_monitor_background_contract(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch)
    mon = rt.monitoring.add(name="disk", kind="disk", config={"path": str(tmp_path), "min_free_gb": 0}, interval_seconds=60)
    result = rt.monitoring.check(mon["monitor_id"])
    assert result["healthy"] is True
    assert rt.monitoring.pause(mon["monitor_id"])["enabled"] is False
    assert rt.monitoring.resume(mon["monitor_id"])["enabled"] is True


def test_rc3_connector_status_never_exposes_secret(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch)
    rt.vault.set("github.token", "super-secret-value")
    row = next(x for x in rt.connectors.list() if x["connector_id"] == "github")
    assert row["credentials"]["ready"] is True
    assert "super-secret-value" not in repr(row)


def test_rc3_mobile_approval_lifecycle(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch)
    device = rt.mobile.register("Phone")
    approval = rt.mobile.request_approval("workspace.merge", {"id": "x"}, mobile_id=device["mobile_id"])
    assert approval["status"] == "pending"
    resolved = rt.mobile.resolve_approval(approval["approval_id"], approved=True)
    assert resolved["status"] == "approved"


def test_rc3_goal_dependencies_and_rollup(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch)
    goal = rt.goals.add("Ship", level="goal")
    project = rt.goals.add("IRAS", level="project", parent_id=goal["item_id"])
    job = rt.goals.add("Build", level="job", parent_id=project["item_id"])
    blocker = rt.goals.add("Prepare", level="task", parent_id=project["item_id"])
    rt.goals.add_dependency(job["item_id"], blocker["item_id"])
    assert rt.goals.ready(job["item_id"]) is False
    rt.goals.update(blocker["item_id"], status="completed", progress=1)
    assert rt.goals.ready(job["item_id"]) is True


def test_rc3_semantic_memory_provenance_and_forget(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch)
    mid = rt.semantic_memory.remember("IRAS provider recovery", namespace="project", source="test")
    found = rt.semantic_memory.search("provider recovery", namespace="project")
    assert found[0]["source"] == "test"
    rt.semantic_memory.forget(mid)
    assert rt.semantic_memory.search("provider recovery", namespace="project") == []


def test_rc3_visual_agent_uses_multiple_evidence_sources():
    agent = AdvancedVisualAgent()
    scene = agent.fuse(
        uia=[{"id": "u1", "text": "Save", "bbox": [10, 10, 100, 50], "actionable": True}],
        accessibility=[{"id": "a1", "text": "Save", "bbox": [10, 10, 100, 50], "actionable": True}],
        omniparser=[{"id": "o1", "text": "Save", "bbox": [11, 11, 99, 49], "confidence": .80, "actionable": True}],
    )
    target = agent.best_target(scene, "Save")
    assert target is not None and target.actionable


def test_rc3_voice_pipeline_wake_and_barge_in():
    voice = FullDuplexVoiceRuntime()
    replies = []
    voice.configure_analysis(voice_activity_detector=lambda audio: True)
    voice.configure_pipeline(transcriber=lambda audio: "IRAS status", dispatcher=lambda text, meta: "Ready", synthesizer=lambda text, cancel: replies.append(text))
    voice.start(); assert voice.feed_audio(b"audio")
    deadline = time.time() + 2
    while not replies and time.time() < deadline:
        time.sleep(.02)
    voice.stop()
    assert replies == ["Ready"]


def test_rc3_isolated_workspace_requires_approval_to_merge(tmp_path, monkeypatch):
    rt = runtime(tmp_path / "state", monkeypatch)
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "a.txt").write_text("one", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    ws = rt.workspace_manager.create(repo, name="change")
    (Path(ws.path) / "a.txt").write_text("two", encoding="utf-8")
    assert "a.txt" in rt.workspace_manager.status(ws.workspace_id)
    try:
        rt.workspace_manager.merge(ws.workspace_id, approved=False)
        assert False, "merge should require approval"
    except PermissionError:
        pass


def test_rc3_status_marks_offline_safe_build(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch)
    status = rt.status()
    assert status["version"] == "5.0.0-rc5"
    assert status["build_mode"] == "offline-safe"
    assert status["remote_protocol"] == 1


def test_rc3_mobile_broadcast_ack_is_per_device_and_legacy_ack_still_works(tmp_path, monkeypatch):
    rt = runtime(tmp_path, monkeypatch)
    phone = rt.mobile.register("Phone")
    tablet = rt.mobile.register("Tablet")
    event_id = rt.mobile.push_event("status", {"ok": True})
    assert [x["event_id"] for x in rt.mobile.pending(phone["mobile_id"])] == [event_id]
    assert [x["event_id"] for x in rt.mobile.pending(tablet["mobile_id"])] == [event_id]
    rt.mobile.acknowledge(event_id, phone["mobile_id"])
    assert rt.mobile.pending(phone["mobile_id"]) == []
    assert [x["event_id"] for x in rt.mobile.pending(tablet["mobile_id"])] == [event_id]
    rt.mobile.acknowledge(event_id)
    assert rt.mobile.pending(tablet["mobile_id"]) == []


def test_rc3_browser_url_validator_returns_url_and_fails_closed():
    from iras.v5.browser_agent import DedicatedBrowserAgent

    assert DedicatedBrowserAgent._validate_url("https://example.com/path?q=1") == "https://example.com/path?q=1"
    assert DedicatedBrowserAgent._validate_url("http://localhost:3000") == "http://localhost:3000"
    assert DedicatedBrowserAgent._validate_url("http://127.0.0.1:8000/health") == "http://127.0.0.1:8000/health"
    for unsafe in ("http://example.com", "file:///etc/passwd", "https://user:pass@example.com", "javascript:alert(1)"):
        try:
            DedicatedBrowserAgent._validate_url(unsafe)
            assert False, unsafe
        except ValueError:
            pass
