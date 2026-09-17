from __future__ import annotations

from pathlib import Path
from typing import Any

from iras.models import PermissionLevel
from iras.tools.base import Tool
from iras.v5.knowledge_graph import ProjectKnowledgeGraph


def _schema(properties=None, required=None):
    return {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False}


def make_tools(v5):
    tools = []
    tools.append(Tool("v5_status", "Show IRAS v5 autonomous capability status.", _schema(), lambda: v5.status(), PermissionLevel.READ))
    tools.append(Tool("v5_goal_list", "List long-term goals/projects/milestones/jobs/tasks.", _schema(), lambda: [v5.goals.get(r["item_id"]) for r in (v5.db.execute("SELECT item_id FROM v5_goals ORDER BY created_at DESC LIMIT 100", fetch="all") or [])], PermissionLevel.READ))
    tools.append(Tool("v5_goal_add", "Add an item to the IRAS goal hierarchy.", _schema({
        "title":{"type":"string","minLength":1,"maxLength":240},"level":{"type":"string","enum":["goal","project","milestone","job","task"]},"parent_id":{"type":"string","maxLength":80}}, ["title"]),
        lambda title, level="goal", parent_id="": v5.goals.add(title, level=level, parent_id=parent_id or None), PermissionLevel.SAFE_ACTION))
    tools.append(Tool("v5_schedule_list", "List persistent autonomous schedules.", _schema(), lambda: v5.scheduler.list(), PermissionLevel.READ))
    tools.append(Tool("v5_schedule_add", "Create a persistent autonomous interval schedule. Scheduled state-changing work remains subject to normal permissions.", _schema({
        "name":{"type":"string","minLength":1,"maxLength":160},"prompt":{"type":"string","minLength":1,"maxLength":12000},"interval_seconds":{"type":"integer","minimum":60,"maximum":31536000}}, ["name","prompt","interval_seconds"]),
        lambda name,prompt,interval_seconds: v5.scheduler.add(name=name,prompt=prompt,interval_seconds=interval_seconds), PermissionLevel.SAFE_ACTION))
    tools.append(Tool("v5_monitor_list", "List proactive monitors.", _schema(), lambda: v5.monitoring.list(), PermissionLevel.READ))
    tools.append(Tool("v5_monitor_add", "Add a proactive HTTPS/API/disk monitor.", _schema({
        "name":{"type":"string","minLength":1,"maxLength":160},"kind":{"type":"string","enum":["website","api","disk"]},"config":{"type":"object"}}, ["name","kind","config"]),
        lambda name,kind,config: v5.monitoring.add(name=name,kind=kind,config=config), PermissionLevel.SAFE_ACTION))
    tools.append(Tool("v5_monitor_check", "Check one proactive monitor now.", _schema({"monitor_id":{"type":"string","minLength":1,"maxLength":80}},["monitor_id"]), lambda monitor_id: v5.monitoring.check(monitor_id), PermissionLevel.READ))
    tools.append(Tool("v5_memory_search", "Search durable semantic project/task memory.", _schema({"query":{"type":"string","minLength":1,"maxLength":2000},"namespace":{"type":"string","maxLength":160},"limit":{"type":"integer","minimum":1,"maximum":50}},["query"]),
        lambda query,namespace="",limit=10: v5.semantic_memory.search(query,namespace=namespace or None,limit=limit), PermissionLevel.READ))
    tools.append(Tool("v5_memory_remember", "Store a durable semantic memory item.", _schema({"text":{"type":"string","minLength":1,"maxLength":50000},"namespace":{"type":"string","maxLength":160},"kind":{"type":"string","maxLength":80}},["text"]),
        lambda text,namespace="default",kind="note": {"memory_id":v5.semantic_memory.remember(text,namespace=namespace,kind=kind)}, PermissionLevel.SAFE_ACTION))
    tools.append(Tool("v5_project_graph_build", "Build a static project knowledge graph from an authorized local repository path.", _schema({"root":{"type":"string","minLength":1,"maxLength":1000}},["root"]),
        lambda root: _build_graph(v5,root), PermissionLevel.READ))
    tools.append(Tool("v5_notification_list", "List IRAS notifications.", _schema({"unread_only":{"type":"boolean"}},[]), lambda unread_only=False: v5.notifications.list(unread_only=unread_only), PermissionLevel.READ))
    tools.append(Tool("v5_notify", "Create an IRAS browser/mobile/desktop notification event.", _schema({"title":{"type":"string","minLength":1,"maxLength":240},"body":{"type":"string","minLength":1,"maxLength":8000},"severity":{"type":"string","enum":["info","warning","error","success"]}},["title","body"]),
        lambda title,body,severity="info": v5.notifications.notify(title,body,severity=severity).__dict__, PermissionLevel.SAFE_ACTION))
    tools.append(Tool("v5_connector_list", "List first-class service connectors and connection state.", _schema(), lambda: v5.connectors.list(), PermissionLevel.READ))
    tools.append(Tool("v5_vault_list", "List symbolic secret names without revealing values.", _schema(), lambda: v5.vault.list(), PermissionLevel.READ))
    tools.append(Tool("v5_vault_reference", "Return a symbolic secret reference; never reveal the secret value.", _schema({"name":{"type":"string","minLength":1,"maxLength":160}},["name"]), lambda name: v5.vault.reference(name), PermissionLevel.READ))
    tools.append(Tool("v5_rollback_list", "List rollback timeline checkpoints.", _schema({"project_root":{"type":"string","maxLength":1000}},[]), lambda project_root="": v5.rollback.list(project_root or None), PermissionLevel.READ))
    tools.append(Tool("v5_rollback_capture", "Capture a Git rollback timeline checkpoint before a project change.", _schema({"project_root":{"type":"string","minLength":1,"maxLength":1000},"label":{"type":"string","maxLength":160}},["project_root"]), lambda project_root,label="checkpoint": v5.rollback.capture(project_root,label), PermissionLevel.SAFE_ACTION))
    tools.append(Tool("v5_rollback_restore", "Restore tracked files to a recorded checkpoint; untracked files are preserved.", _schema({"checkpoint_id":{"type":"string","minLength":1,"maxLength":80},"approved":{"type":"boolean"}},["checkpoint_id","approved"]), lambda checkpoint_id,approved: v5.rollback.restore_tracked(checkpoint_id,approved=approved), PermissionLevel.CRITICAL))
    tools.append(Tool("v5_audit_summary", "Summarize recent IRAS activity/audit traces.", _schema({"limit":{"type":"integer","minimum":1,"maximum":2000}},[]), lambda limit=500: v5.audit.summary(limit), PermissionLevel.READ))
    return tools


def _build_graph(v5, root: str):
    graph = ProjectKnowledgeGraph(root)
    summary = graph.build()
    out = v5.state_dir / "knowledge"
    out.mkdir(parents=True, exist_ok=True)
    path = out / (Path(root).name + ".json")
    graph.export(path)
    return {**summary, "snapshot": str(path)}
