from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess

import pytest

from iras.v5.runtime import V5Runtime, FEATURES
from iras.v5.common import SQLiteDB, EventBus
from iras.v5.scheduler import PersistentScheduler
from iras.v5.monitoring import ProactiveMonitor, MonitorResult
from iras.v5.visual_agent import AdvancedVisualAgent
from iras.v5.browser_agent import DedicatedBrowserAgent
from iras.v5.workflow import WorkflowRecorder
from iras.v5.semantic_memory import SemanticMemory
from iras.v5.knowledge_graph import ProjectKnowledgeGraph
from iras.v5.coding_workspace import CodingWorkspaceManager
from iras.v5.self_healing import SelfHealingEngine, RecoveryStrategy
from iras.v5.capability_learning import CapabilityLearner
from iras.v5.connectors import ConnectorRegistry
from iras.v5.voice_runtime import FullDuplexVoiceRuntime
from iras.v5.mobile import MobileCompanionHub
from iras.v5.notifications import NotificationCenter
from iras.v5.artifacts import ArtifactEngine
from iras.v5.vault import SecretVault
from iras.v5.sandbox import SandboxRunner
from iras.v5.research import AutonomousResearchEngine
from iras.v5.debate import AgentDebate
from iras.v5.resource_router import ResourceAwareRouter, ResourceSnapshot
from iras.v5.rollback import RollbackTimeline
from iras.v5.audit_dashboard import AuditDashboard
from iras.v5.skills import SkillMarketplace, SkillManifest
from iras.v5.home_network import HomeNetworkHub
from iras.v5.profiles import ProfileStore
from iras.v5.encrypted_sync import EncryptedSync
from iras.v5.goals import GoalHierarchy


def _db(tmp_path):
    return SQLiteDB(tmp_path / "state.db")


def _git(repo: Path, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return p.stdout.strip()


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"; repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "iras@test.local")
    _git(repo, "config", "user.name", "IRAS Test")
    (repo / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    (repo / "tests").mkdir(); (repo / "tests" / "test_app.py").write_text("from app import hello\n\ndef test_hello(): assert hello() == 'hi'\n", encoding="utf-8")
    (repo / "schema.sql").write_text("CREATE TABLE users(id INTEGER PRIMARY KEY);\n", encoding="utf-8")
    (repo / "Dockerfile").write_text("FROM python:3.13-slim\n", encoding="utf-8")
    _git(repo, "add", "."); _git(repo, "commit", "-m", "init")
    return repo


def test_v5_feature_inventory(tmp_path, monkeypatch):
    monkeypatch.setenv("IRAS_VAULT_MASTER_KEY", EncryptedSync.new_key())
    rt = V5Runtime(tmp_path / "v5")
    status = rt.status()
    assert status["version"] == "5.0.0-rc3"
    assert status["feature_count"] == 34
    assert set(status["features"]) == set(FEATURES)
    assert status["persistent_backend"] == "sqlite"


def test_persistent_scheduler_survives_restart(tmp_path):
    db = _db(tmp_path); a = PersistentScheduler(db)
    row = a.add(name="daily brief", prompt="brief me", interval_seconds=3600)
    b = PersistentScheduler(_db(tmp_path))
    assert b.get(row["job_id"])["prompt"] == "brief me"
    results = b.run_due(lambda prompt, meta: "done:" + prompt)
    assert results[0]["ok"] is True
    assert b.get(row["job_id"])["last_result"] == "done:brief me"


def test_proactive_monitor_notifies_only_on_change(tmp_path):
    db = _db(tmp_path); bus = EventBus(); mon = ProactiveMonitor(db, bus)
    state = {"v": 1}
    mon.register_checker("fake", lambda cfg: MonitorResult({"value": state["v"]}, True, str(state["v"])))
    row = mon.add(name="x", kind="fake", config={})
    assert mon.check(row["monitor_id"])["first"] is True
    assert mon.check(row["monitor_id"])["changed"] is False
    state["v"] = 2
    assert mon.check(row["monitor_id"])["changed"] is True
    assert any(e["topic"] == "monitor.changed" for e in bus.recent())


def test_visual_agent_fuses_uia_and_omniparser():
    agent = AdvancedVisualAgent()
    scene = agent.fuse(
        uia=[{"id": "save", "text": "Save", "role": "button", "bbox": [1,2,3,4], "actionable": True}],
        omniparser=[{"id": "cancel", "text": "Cancel", "confidence": .92, "bbox": [5,6,7,8], "actionable": True}],
        screenshot_path="screen.png", title="Editor",
    )
    assert agent.best_target(scene, "Save").element_id == "save"
    assert agent.best_target(scene, "Cancel").actionable is True


def test_browser_agent_enforces_https(tmp_path):
    browser = DedicatedBrowserAgent(tmp_path)
    with pytest.raises(ValueError):
        browser.start(headless=True) if False else browser.navigate("http://example.com")


def test_workflow_record_and_replay(tmp_path):
    rec = WorkflowRecorder(tmp_path)
    rec.begin("open and type"); rec.record("open_app", {"app": "notepad"}); rec.record("type", {"text": "hi"})
    wf = rec.finish(); calls=[]
    out = rec.replay(wf.workflow_id, lambda action, args: calls.append((action,args)) or action)
    assert out == ["open_app", "type"] and calls[1][1]["text"] == "hi"


def test_semantic_memory_search(tmp_path):
    mem = SemanticMemory(_db(tmp_path)); mem.remember("IRAS provider cooldown recovery fixed", namespace="iras", kind="fix")
    mem.remember("unrelated cooking note", namespace="iras")
    rows = mem.search("provider recovery", namespace="iras")
    assert rows and "cooldown" in rows[0]["text"]


def test_project_knowledge_graph_maps_code_routes_db_and_deploy(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "api.py").write_text("from fastapi import FastAPI\napp=FastAPI()\n@app.get('/health')\ndef health(): return {'ok':True}\n", encoding="utf-8")
    kg = ProjectKnowledgeGraph(repo); summary = kg.build()
    assert summary["test_modules"] >= 1
    assert summary["routes"] >= 1
    assert summary["database_tables"] >= 1
    assert kg.search("health")
    assert kg.search("Dockerfile")


def test_isolated_coding_workspace(tmp_path):
    repo = _make_repo(tmp_path); mgr = CodingWorkspaceManager(tmp_path / "worktrees")
    ws = mgr.create(repo, name="safe fix")
    try:
        p = Path(ws.path) / "app.py"; p.write_text("def hello():\n    return 'hello'\n", encoding="utf-8")
        assert "app.py" in mgr.status(ws)
        assert "hello" in mgr.diff(ws)
        assert mgr.merge_plan(ws)["branch"].startswith("iras/")
    finally:
        mgr.remove(ws, delete_branch=True)


def test_self_healing_learns_strategy_success(tmp_path):
    engine = SelfHealingEngine(_db(tmp_path)); calls=[]
    engine.register(RecoveryStrategy("retry", "timeout", lambda ctx: calls.append(ctx) or "ok"))
    result = engine.recover("Timeout while fetching", {"x":1})
    assert result["recovered"] and result["strategy"] == "retry" and calls


def test_capability_learning_requires_test_and_approval(tmp_path):
    learner = CapabilityLearner(tmp_path)
    p = learner.propose(name="hello_skill", description="x", source="VALUE=1", tests="")
    p = learner.test(p.proposal_id, lambda src, tests: {"ok": "VALUE=1" in src})
    assert p.status == "tested"
    with pytest.raises(PermissionError): learner.approve_install(p.proposal_id, approved=False)
    assert learner.approve_install(p.proposal_id, approved=True).exists()


def test_connector_layer_has_first_class_services():
    reg = ConnectorRegistry(); ids = {x["connector_id"] for x in reg.list()}
    assert {"gmail","calendar","drive","github","supabase","discord","slack","notion"} <= ids
    with pytest.raises(PermissionError): reg.invoke("github", "repos.read")


def test_full_duplex_voice_barge_in_and_analysis():
    v = FullDuplexVoiceRuntime(); v.configure_analysis(speaker_identifier=lambda b:"hamza",prosody_analyzer=lambda b:{"energy":.8},voice_activity_detector=lambda b:True)
    assert v.detect_wake("IRAS hello")
    analysis=v.analyze_audio(b"x"); assert analysis["speaker_id"]=="hamza" and analysis["speech"] is True
    cancel=v.begin_speaking(); assert v.barge_in() is True and cancel.is_set()


def test_mobile_companion_event_queue(tmp_path):
    hub=MobileCompanionHub(_db(tmp_path)); dev=hub.register("Phone")
    eid=hub.push_event("approval",{"action":"deploy"},dev["mobile_id"])
    assert hub.pending(dev["mobile_id"])[0]["event_id"]==eid
    hub.acknowledge(eid); assert hub.pending(dev["mobile_id"])==[]


def test_notification_center(tmp_path):
    sent=[]; center=NotificationCenter(_db(tmp_path)); center.register_channel("browser",lambda n:sent.append(n.title))
    center.notify("Job complete","done")
    assert sent==["Job complete"] and center.list(unread_only=True)


def test_artifact_engine_creates_all_major_formats(tmp_path):
    eng=ArtifactEngine(tmp_path)
    paths=[eng.document("report",["hello"]),eng.pdf("report",["hello"]),eng.spreadsheet("data",[["a",1]]),eng.presentation("deck",[{"title":"T","body":"B"}])]
    bundle=eng.bundle("bundle",paths)
    assert all(Path(p).exists() and Path(p).stat().st_size>0 for p in paths+[bundle])


def test_secure_vault_uses_encryption(tmp_path, monkeypatch):
    key=EncryptedSync.new_key(); vault=SecretVault(tmp_path/"vault.json",master_key=key)
    vault.set("github.token","super-secret")
    assert vault.get("github.token")=="super-secret"
    raw=(tmp_path/"vault.json").read_text(); assert "super-secret" not in raw and "github.token" in vault.list()
    assert vault.reference("github.token")=={"secret_ref":"github.token"}


def test_sandbox_local_fallback_is_explicit(tmp_path):
    runner=SandboxRunner(allow_local_fallback=True)
    if runner.docker_available:
        pytest.skip("Docker behavior is environment-dependent in unit test")
    result=runner.run_python("VALUE=1","import capability\nassert capability.VALUE==1\nprint('ok')")
    assert result["ok"] and result["backend"]=="local-isolated-process"


def test_autonomous_research_and_debate():
    research=AutonomousResearchEngine().run("q",[lambda q:{"findings":[{"claim":"A","evidence":"E","source":"https://x","confidence":.9}]}])
    assert research.findings[0].claim=="A"
    debate=AgentDebate().run("fix",proposer=lambda o:"p",challenger=lambda o,p:"c",tester=lambda o,p,c:"t",coordinator=lambda o,p,c,t:"accept")
    assert debate["decision"]=="accept"


def test_resource_aware_intelligence_prefers_healthier():
    r=ResourceAwareRouter().choose([
        {"name":"slow","state":"ONLINE","latency_ms":1500,"failure_rate":.2},
        {"name":"fast","state":"ONLINE","latency_ms":100,"failure_rate":0},
    ],resources=ResourceSnapshot(ram_free_mb=8000))
    assert r["name"]=="fast"


def test_rollback_timeline_restores_tracked_files(tmp_path):
    repo=_make_repo(tmp_path); timeline=RollbackTimeline(_db(tmp_path)); cp=timeline.capture(repo,"before")
    (repo/"app.py").write_text("BROKEN=1\n",encoding="utf-8")
    timeline.restore_tracked(cp["checkpoint_id"],approved=True)
    assert "def hello" in (repo/"app.py").read_text()


def test_activity_audit_dashboard(tmp_path):
    p=tmp_path/"trace.jsonl"; p.write_text('{"name":"tool_call","ok":true}\n{"name":"tool_error","ok":false,"error":"x"}\n')
    s=AuditDashboard(p).summary(); assert s["events"]==2 and s["errors"]==1


def test_signed_skill_marketplace(tmp_path):
    cryptography = pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    key=Ed25519PrivateKey.generate(); pub=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    m=SkillManifest("demo","1.0","demo",["READ"],"skill.py","tester")
    files={"skill.py":"VALUE=1"}
    sig=key.sign(SkillMarketplace._payload(m, files))
    market=SkillMarketplace(tmp_path)
    target=market.install(m,files,signature_b64=base64.b64encode(sig).decode(),public_key_b64=base64.b64encode(pub).decode(),approved=True)
    assert Path(target,"skill.py").exists()


def test_home_network_allowlist_and_approval():
    class Adapter:
        allowed_actions=("status","switch")
        read_only_actions=("status",)
        def status(self,host): return "ok"
        def switch(self,host,on): return on
    hub=HomeNetworkHub(["192.168.1.0/24"]); hub.register("lamp",Adapter())
    assert hub.invoke("lamp","status",host="192.168.1.10")=="ok"
    with pytest.raises(PermissionError): hub.invoke("lamp","switch",host="192.168.1.10",on=True)
    assert hub.invoke("lamp","switch",host="192.168.1.10",on=True,approval=lambda n,a:True) is True
    with pytest.raises(PermissionError): hub.invoke("lamp","status",host="8.8.8.8")


def test_multi_user_profiles(tmp_path):
    store=ProfileStore(_db(tmp_path)); a=store.create("Hamza",["read","control"]); b=store.create("Guest",["read"])
    assert a["memory_namespace"]!=b["memory_namespace"] and store.get(b["profile_id"])["permissions"]==["read"]


def test_encrypted_sync_roundtrip():
    key=EncryptedSync.new_key(); blob=EncryptedSync.encrypt({"goals":[1,2],"memory":"x"},key)
    assert b"memory" not in blob and EncryptedSync.decrypt(blob,key)["goals"]==[1,2]


def test_goal_hierarchy(tmp_path):
    goals=GoalHierarchy(_db(tmp_path)); g=goals.add("Graduate",level="goal"); p=goals.add("IRAS",level="project",parent_id=g["item_id"]); m=goals.add("v5",level="milestone",parent_id=p["item_id"])
    goals.update(m["item_id"],status="active",progress=.25)
    tree=goals.tree(g["item_id"])
    assert tree["children"][0]["children"][0]["status"]=="active"


def test_cloud_source_exposes_v5_control_surface():
    text=Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    for route in ("/v1/v5/status","/v1/v5/goals","/v1/v5/schedules","/v1/v5/monitors","/v1/v5/notifications","/v1/v5/audit","/v1/v5/connectors"):
        assert route in text
    web=Path("clients/web/index.html").read_text(encoding="utf-8")
    assert "IRAS Autonomy Control Center" in web and "v5control" in web
