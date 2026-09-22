from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from iras.models import PermissionLevel
from iras.tools.base import Tool
from iras.v5.knowledge_graph import ProjectKnowledgeGraph
from iras.v5.resource_router import ResourceSnapshot
from iras.v5.skills import SkillManifest


def _schema(properties=None, required=None, *, additional=False):
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": bool(additional),
    }


def _obj():
    return {"type": "object", "additionalProperties": True}


def _str(max_len=4000):
    return {"type": "string", "maxLength": max_len}


def _connector_permission(args: dict[str, Any]) -> PermissionLevel:
    capability = str(args.get("capability") or "").lower()
    if any(token in capability for token in ("send", "write", "create", "update", "delete", "mutate")):
        return PermissionLevel.SYSTEM_ACTION
    return PermissionLevel.READ


def make_tools(v5):
    """Expose every RC3 operating-layer subsystem through the v4 permission core.

    The handlers deliberately do not accept raw credentials. Connector and sync
    secrets are referenced symbolically and resolved only inside the secure vault.
    """

    t: list[Tool] = []
    add = t.append

    # Operating-layer / release / migrations -------------------------------------------------
    add(Tool("v5_status", "Show complete IRAS v5 operating-layer and feature status.", _schema(), lambda: v5.status(), PermissionLevel.READ))
    add(Tool("v5_feature_status", "Show whether every declared RC3 feature surface is operational.", _schema(), lambda: v5.feature_status(), PermissionLevel.READ))
    add(Tool("v5_migration_status", "Show schema migration ledger and current migration state.", _schema(), lambda: v5.migrations.status(), PermissionLevel.READ))

    # Goal hierarchy -------------------------------------------------------------------------
    add(Tool("v5_goal_list", "List long-term goals/projects/milestones/jobs/tasks.", _schema(), lambda: [v5.goals.get(r["item_id"]) for r in (v5.db.execute("SELECT item_id FROM v5_goals ORDER BY created_at DESC LIMIT 100", fetch="all") or [])], PermissionLevel.READ))
    add(Tool("v5_goal_add", "Add an item to the IRAS goal hierarchy.", _schema({"title": {"type": "string", "minLength": 1, "maxLength": 240}, "level": {"type": "string", "enum": ["goal", "project", "milestone", "job", "task"]}, "parent_id": _str(80)}, ["title"]), lambda title, level="goal", parent_id="": v5.goals.add(title, level=level, parent_id=parent_id or None), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_goal_dependency", "Add a dependency between goal-hierarchy items.", _schema({"item_id": _str(80), "depends_on": _str(80)}, ["item_id", "depends_on"]), lambda item_id, depends_on: (v5.goals.add_dependency(item_id, depends_on) or {"ok": True}), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_goal_update", "Update goal/task status or progress.", _schema({"item_id": _str(80), "status": _str(80), "progress": {"type": "number", "minimum": 0, "maximum": 1}}, ["item_id"]), lambda item_id, status="", progress=None: v5.goals.update(item_id, status=status or None, progress=progress), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_goal_tree", "Read one goal subtree.", _schema({"item_id": _str(80)}, ["item_id"]), lambda item_id: v5.goals.tree(item_id), PermissionLevel.READ))
    add(Tool("v5_goal_next", "List goal/job/task items whose dependencies are satisfied.", _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 100}}), lambda limit=20: v5.goals.next_actions(limit), PermissionLevel.READ))

    # Scheduler ------------------------------------------------------------------------------
    add(Tool("v5_schedule_list", "List persistent autonomous schedules.", _schema(), lambda: v5.scheduler.list(), PermissionLevel.READ))
    add(Tool("v5_schedule_add", "Create a restart-safe autonomous interval schedule; scheduled execution remains read-only by default.", _schema({"name": {"type": "string", "minLength": 1, "maxLength": 160}, "prompt": {"type": "string", "minLength": 1, "maxLength": 12000}, "interval_seconds": {"type": "integer", "minimum": 60, "maximum": 31536000}}, ["name", "prompt", "interval_seconds"]), lambda name, prompt, interval_seconds: v5.scheduler.add(name=name, prompt=prompt, interval_seconds=interval_seconds), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_schedule_pause", "Pause a persistent schedule.", _schema({"job_id": _str(100)}, ["job_id"]), lambda job_id: v5.scheduler.pause(job_id), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_schedule_resume", "Resume a persistent schedule.", _schema({"job_id": _str(100)}, ["job_id"]), lambda job_id: v5.scheduler.resume(job_id), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_schedule_cancel", "Cancel a persistent schedule without deleting its audit record.", _schema({"job_id": _str(100)}, ["job_id"]), lambda job_id: (v5.scheduler.cancel(job_id) or {"cancelled": job_id}), PermissionLevel.SYSTEM_ACTION))

    # Monitoring -----------------------------------------------------------------------------
    add(Tool("v5_monitor_list", "List proactive monitors.", _schema(), lambda: v5.monitoring.list(), PermissionLevel.READ))
    add(Tool("v5_monitor_add", "Add a proactive HTTPS/API/disk monitor.", _schema({"name": {"type": "string", "minLength": 1, "maxLength": 160}, "kind": {"type": "string", "enum": ["website", "api", "disk"]}, "config": _obj(), "interval_seconds": {"type": "integer", "minimum": 60, "maximum": 86400}}, ["name", "kind", "config"]), lambda name, kind, config, interval_seconds=300: v5.monitoring.add(name=name, kind=kind, config=config, interval_seconds=interval_seconds), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_monitor_check", "Check one proactive monitor now.", _schema({"monitor_id": _str(100)}, ["monitor_id"]), lambda monitor_id: v5.monitoring.check(monitor_id), PermissionLevel.READ))
    add(Tool("v5_monitor_check_all", "Check all proactive monitors now.", _schema(), lambda: v5.monitoring.check_all(), PermissionLevel.READ))
    add(Tool("v5_monitor_pause", "Pause a proactive monitor.", _schema({"monitor_id": _str(100)}, ["monitor_id"]), lambda monitor_id: v5.monitoring.pause(monitor_id), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_monitor_resume", "Resume a proactive monitor.", _schema({"monitor_id": _str(100)}, ["monitor_id"]), lambda monitor_id: v5.monitoring.resume(monitor_id), PermissionLevel.SAFE_ACTION))

    # Memory + knowledge graph ---------------------------------------------------------------
    add(Tool("v5_memory_search", "Search durable semantic project/task memory.", _schema({"query": {"type": "string", "minLength": 1, "maxLength": 2000}, "namespace": _str(160), "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, ["query"]), lambda query, namespace="", limit=10: v5.semantic_memory.search(query, namespace=namespace or None, limit=limit), PermissionLevel.READ))
    add(Tool("v5_memory_remember", "Store durable semantic memory with provenance.", _schema({"text": {"type": "string", "minLength": 1, "maxLength": 50000}, "namespace": _str(160), "kind": _str(80), "source": _str(240)}, ["text"]), lambda text, namespace="default", kind="note", source="agent": {"memory_id": v5.semantic_memory.remember(text, namespace=namespace, kind=kind, source=source)}, PermissionLevel.SAFE_ACTION))
    add(Tool("v5_memory_forget", "Delete one durable memory item.", _schema({"memory_id": _str(100)}, ["memory_id"]), lambda memory_id: (v5.semantic_memory.forget(memory_id) or {"forgotten": memory_id}), PermissionLevel.CRITICAL))
    add(Tool("v5_project_graph_build", "Build a static project knowledge graph from an authorized local repository path.", _schema({"root": {"type": "string", "minLength": 1, "maxLength": 1000}}, ["root"]), lambda root: _build_graph(v5, root), PermissionLevel.READ))

    # Coding workspaces ----------------------------------------------------------------------
    add(Tool("v5_workspace_list", "List isolated coding workspaces.", _schema(), lambda: v5.workspace_manager.list(), PermissionLevel.READ))
    add(Tool("v5_workspace_create", "Create an isolated Git worktree/branch for coding.", _schema({"repo": {"type": "string", "minLength": 1, "maxLength": 1000}, "name": {"type": "string", "minLength": 1, "maxLength": 120}, "base_ref": _str(120)}, ["repo", "name"]), lambda repo, name, base_ref="HEAD": v5.workspace_manager.create(repo, name=name, base_ref=base_ref).__dict__, PermissionLevel.SAFE_ACTION))
    add(Tool("v5_workspace_status", "Show one isolated coding workspace status.", _schema({"workspace_id": _str(100)}, ["workspace_id"]), lambda workspace_id: {"status": v5.workspace_manager.status(workspace_id)}, PermissionLevel.READ))
    add(Tool("v5_workspace_diff", "Show the diff for an isolated coding workspace.", _schema({"workspace_id": _str(100), "staged": {"type": "boolean"}}, ["workspace_id"]), lambda workspace_id, staged=False: {"diff": v5.workspace_manager.diff(workspace_id, staged=staged)}, PermissionLevel.READ))
    add(Tool("v5_workspace_commits", "Show recent commits in an isolated coding workspace.", _schema({"workspace_id": _str(100), "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ["workspace_id"]), lambda workspace_id, limit=20: v5.workspace_manager.commits(workspace_id, limit), PermissionLevel.READ))
    add(Tool("v5_workspace_test", "Run targeted pytest inside an isolated coding workspace.", _schema({"workspace_id": _str(100), "args": {"type": "array", "items": _str(500), "maxItems": 32}}, ["workspace_id"]), lambda workspace_id, args=None: v5.workspace_manager.run_tests(workspace_id, args or ["-q"]), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_workspace_commit", "Commit changes inside an isolated coding workspace.", _schema({"workspace_id": _str(100), "message": {"type": "string", "minLength": 1, "maxLength": 240}}, ["workspace_id", "message"]), lambda workspace_id, message: v5.workspace_manager.commit(workspace_id, message), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_workspace_merge_plan", "Show, but do not execute, an isolated-workspace merge plan.", _schema({"workspace_id": _str(100)}, ["workspace_id"]), lambda workspace_id: v5.workspace_manager.merge_plan(workspace_id), PermissionLevel.READ))
    add(Tool("v5_workspace_merge", "Merge an isolated workspace only after explicit approval.", _schema({"workspace_id": _str(100), "approved": {"type": "boolean"}}, ["workspace_id", "approved"]), lambda workspace_id, approved: v5.workspace_manager.merge(workspace_id, approved=approved), PermissionLevel.CRITICAL))
    add(Tool("v5_workspace_remove", "Remove an isolated worktree after explicit approval.", _schema({"workspace_id": _str(100), "delete_branch": {"type": "boolean"}}, ["workspace_id"]), lambda workspace_id, delete_branch=False: (v5.workspace_manager.remove(workspace_id, delete_branch=delete_branch) or {"removed": workspace_id}), PermissionLevel.CRITICAL))

    # Workflow recording / replay ------------------------------------------------------------
    add(Tool("v5_workflow_list", "List recorded reusable workflows.", _schema(), lambda: v5.workflows.list(), PermissionLevel.READ))
    add(Tool("v5_workflow_begin", "Begin recording a reusable workflow.", _schema({"name": {"type": "string", "minLength": 1, "maxLength": 160}}, ["name"]), lambda name: (v5.workflows.begin(name) or {"recording": name}), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_workflow_record", "Append a tool/action step to the active workflow recording.", _schema({"action": _str(160), "arguments": _obj(), "verify": _obj()}, ["action"]), lambda action, arguments=None, verify=None: (v5.workflows.record(action, arguments or {}, verify or {}) or {"recorded": action}), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_workflow_finish", "Finish the active workflow recording.", _schema(), lambda: v5.workflows.finish().as_dict(), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_workflow_replay", "Replay a recorded workflow through the normal ToolRegistry permission gates.", _schema({"workflow_id": _str(100)}, ["workflow_id"]), lambda workflow_id: v5.replay_workflow(workflow_id), PermissionLevel.SYSTEM_ACTION))

    # Notifications / mobile companion -------------------------------------------------------
    add(Tool("v5_notification_list", "List IRAS notifications.", _schema({"unread_only": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}), lambda unread_only=False, limit=100: v5.notifications.list(unread_only=unread_only, limit=limit), PermissionLevel.READ))
    add(Tool("v5_notify", "Create an IRAS browser/mobile/desktop notification event.", _schema({"title": {"type": "string", "minLength": 1, "maxLength": 240}, "body": {"type": "string", "minLength": 1, "maxLength": 8000}, "severity": {"type": "string", "enum": ["info", "warning", "error", "success"]}, "channel": {"type": "string", "enum": ["browser", "mobile", "desktop"]}}, ["title", "body"]), lambda title, body, severity="info", channel="browser": asdict(v5.notifications.notify(title, body, severity=severity, channel=channel)), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_notification_mark_read", "Mark one notification read.", _schema({"notification_id": _str(100)}, ["notification_id"]), lambda notification_id: (v5.notifications.mark_read(notification_id) or {"read": notification_id}), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_mobile_devices", "List paired mobile companion devices.", _schema(), lambda: v5.mobile.list_devices(), PermissionLevel.READ))
    add(Tool("v5_mobile_approvals", "List mobile approval requests.", _schema({"status": {"type": "string", "enum": ["pending", "approved", "denied"]}}, []), lambda status="": v5.mobile.approvals(status=status or None), PermissionLevel.READ))
    add(Tool("v5_mobile_request_approval", "Send a permission/decision request to the Android companion.", _schema({"kind": {"type": "string", "minLength": 1, "maxLength": 160}, "payload": _obj(), "mobile_id": _str(100)}, ["kind", "payload"]), lambda kind, payload, mobile_id="": v5.mobile.request_approval(kind, payload, mobile_id=mobile_id or None), PermissionLevel.SAFE_ACTION))

    # Connectors + symbolic vault ------------------------------------------------------------
    add(Tool("v5_connector_list", "List service connectors, authorization state and symbolic credential readiness.", _schema(), lambda: v5.connectors.list(), PermissionLevel.READ))
    add(Tool("v5_connector_configure", "Configure a connector using symbolic vault references only; never accepts raw secrets.", _schema({"connector_id": _str(80), "secret_refs": {"type": "object", "additionalProperties": _str(160)}, "scopes": {"type": "array", "items": _str(160), "maxItems": 64}, "account_label": _str(240), "expires_at": _str(80)}, ["connector_id"]), lambda connector_id, secret_refs=None, scopes=None, account_label="", expires_at="": v5.connectors.configure(connector_id, secret_refs=secret_refs or {}, scopes=scopes or [], account_label=account_label, expires_at=expires_at or None), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_connector_authorize", "Mark connector authorization ready after its referenced secrets have been provisioned.", _schema({"connector_id": _str(80), "secret_refs": {"type": "object", "additionalProperties": _str(160)}, "scopes": {"type": "array", "items": _str(160), "maxItems": 64}, "account_label": _str(240), "expires_at": _str(80)}, ["connector_id"]), lambda connector_id, secret_refs=None, scopes=None, account_label="", expires_at="": v5.connectors.authorize(connector_id, secret_refs=secret_refs, scopes=scopes, account_label=account_label, expires_at=expires_at or None), PermissionLevel.CRITICAL))
    add(Tool("v5_connector_connect", "Instantiate an authorized built-in connector adapter.", _schema({"connector_id": _str(80)}, ["connector_id"]), lambda connector_id: v5.connectors.connect_builtin(connector_id), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_connector_disconnect", "Disconnect a connector adapter without deleting authorization metadata.", _schema({"connector_id": _str(80)}, ["connector_id"]), lambda connector_id: (v5.connectors.detach(connector_id) or v5.connectors.status(connector_id)), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_connector_invoke", "Invoke one declared connector capability. Read capabilities stay read-only; send/write capabilities require stronger approval.", _schema({"connector_id": _str(80), "capability": _str(160), "arguments": _obj()}, ["connector_id", "capability"]), lambda connector_id, capability, arguments=None: v5.connectors.invoke(connector_id, capability, **(arguments or {})), PermissionLevel.READ, permission_resolver=_connector_permission))
    add(Tool("v5_vault_list", "List symbolic secret names without revealing values.", _schema(), lambda: v5.vault.list(), PermissionLevel.READ))
    add(Tool("v5_vault_reference", "Return a symbolic secret reference; never reveal the secret value.", _schema({"name": {"type": "string", "minLength": 1, "maxLength": 160}}, ["name"]), lambda name: v5.vault.reference(name), PermissionLevel.READ))

    # Dedicated browser workflow agent -------------------------------------------------------
    add(Tool("v5_browser_start", "Start the dedicated Playwright browser agent.", _schema({"headless": {"type": "boolean"}, "profile": _str(120)}), lambda headless=True, profile="default": (_browser_start(v5, headless, profile)), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_browser_stop", "Stop the dedicated browser agent.", _schema(), lambda: (v5.browser.stop() or {"stopped": True}), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_browser_tabs", "List dedicated browser-agent tabs.", _schema(), lambda: v5.browser.tabs(), PermissionLevel.READ))
    add(Tool("v5_browser_new_tab", "Open a new browser tab, optionally at an HTTPS URL.", _schema({"url": _str(2000)}), lambda url="": {"tab_id": v5.browser.new_tab(url)[0]}, PermissionLevel.SAFE_ACTION))
    add(Tool("v5_browser_close_tab", "Close a dedicated browser tab.", _schema({"tab_id": _str(100)}, ["tab_id"]), lambda tab_id: (v5.browser.close_tab(tab_id) or {"closed": tab_id}), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_browser_navigate", "Navigate the dedicated browser agent to an HTTPS URL.", _schema({"url": {"type": "string", "minLength": 1, "maxLength": 2000}, "tab_id": _str(100)}, ["url"]), lambda url, tab_id="": _browser_navigate_with_heal(v5, url, tab_id or None), PermissionLevel.READ))
    add(Tool("v5_browser_extract", "Extract bounded visible text from the dedicated browser.", _schema({"selector": _str(1000), "tab_id": _str(100), "limit": {"type": "integer", "minimum": 1, "maximum": 100000}}), lambda selector="body", tab_id="", limit=30000: {"text": v5.browser.extract(selector, tab_id=tab_id or None, limit=limit)}, PermissionLevel.READ))
    add(Tool("v5_browser_verify", "Verify browser URL/text/selector state.", _schema({"url_contains": _str(1000), "text_contains": _str(5000), "selector": _str(1000), "tab_id": _str(100)}), lambda url_contains="", text_contains="", selector="", tab_id="": v5.browser.verify(url_contains=url_contains, text_contains=text_contains, selector=selector, tab_id=tab_id or None), PermissionLevel.READ))
    add(Tool("v5_browser_fill", "Fill one browser DOM field without submitting it.", _schema({"selector": _str(1000), "value": _str(20000), "tab_id": _str(100)}, ["selector", "value"]), lambda selector, value, tab_id="": (v5.browser.fill(selector, value, tab_id=tab_id or None) or {"filled": selector}), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_browser_click", "Click one browser DOM element. State-changing sites still require the normal permission gate.", _schema({"selector": _str(1000), "tab_id": _str(100)}, ["selector"]), lambda selector, tab_id="": (v5.browser.click(selector, tab_id=tab_id or None) or {"clicked": selector}), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_browser_upload", "Attach a local file to one browser file input.", _schema({"selector": _str(1000), "path": _str(1000), "tab_id": _str(100)}, ["selector", "path"]), lambda selector, path, tab_id="": (v5.browser.upload(selector, path, tab_id=tab_id or None) or {"uploaded": path}), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_browser_submit", "Submit one browser element only after critical approval.", _schema({"selector": _str(1000), "tab_id": _str(100)}, ["selector"]), lambda selector, tab_id="": (v5.browser.submit(selector, approved=True, tab_id=tab_id or None) or {"submitted": selector}), PermissionLevel.CRITICAL))

    # Voice + visual fusion ------------------------------------------------------------------
    add(Tool("v5_voice_status", "Inspect full-duplex voice runtime state and recent turn count.", _schema(), lambda: _voice_status(v5), PermissionLevel.READ))
    add(Tool("v5_voice_barge_in", "Interrupt current IRAS speech output.", _schema(), lambda: {"interrupted": v5.voice.barge_in()}, PermissionLevel.SAFE_ACTION))
    add(Tool("v5_visual_fuse", "Fuse UIA, accessibility and OmniParser evidence into a conservative scene graph.", _schema({"uia": {"type": "array", "items": _obj(), "maxItems": 2000}, "accessibility": {"type": "array", "items": _obj(), "maxItems": 2000}, "omniparser": {"type": "array", "items": _obj(), "maxItems": 2000}, "title": _str(500), "screenshot_path": _str(1000)}), lambda uia=None, accessibility=None, omniparser=None, title="", screenshot_path="": v5.visual.fuse(uia=uia, accessibility=accessibility, omniparser=omniparser, title=title, screenshot_path=screenshot_path).as_dict(), PermissionLevel.READ))

    # Artifacts ------------------------------------------------------------------------------
    add(Tool("v5_artifact_list", "List artifacts generated inside the v5 artifact workspace.", _schema(), lambda: v5.artifacts.list(), PermissionLevel.READ))
    add(Tool("v5_artifact_document", "Create a DOCX artifact inside the controlled artifact workspace.", _schema({"name": _str(180), "paragraphs": {"type": "array", "items": _str(50000), "maxItems": 1000}}, ["name", "paragraphs"]), lambda name, paragraphs: {"path": v5.artifacts.document(name, paragraphs)}, PermissionLevel.SAFE_ACTION))
    add(Tool("v5_artifact_pdf", "Create a PDF artifact inside the controlled artifact workspace.", _schema({"name": _str(180), "lines": {"type": "array", "items": _str(20000), "maxItems": 3000}}, ["name", "lines"]), lambda name, lines: {"path": v5.artifacts.pdf(name, lines)}, PermissionLevel.SAFE_ACTION))
    add(Tool("v5_artifact_spreadsheet", "Create an XLSX artifact inside the controlled artifact workspace.", _schema({"name": _str(180), "rows": {"type": "array", "items": {"type": "array", "maxItems": 256}, "maxItems": 10000}}, ["name", "rows"]), lambda name, rows: {"path": v5.artifacts.spreadsheet(name, rows)}, PermissionLevel.SAFE_ACTION))
    add(Tool("v5_artifact_presentation", "Create a PPTX artifact inside the controlled artifact workspace.", _schema({"name": _str(180), "slides": {"type": "array", "items": _obj(), "maxItems": 500}}, ["name", "slides"]), lambda name, slides: {"path": v5.artifacts.presentation(name, slides)}, PermissionLevel.SAFE_ACTION))
    add(Tool("v5_artifact_bundle", "Bundle controlled artifact files into a ZIP.", _schema({"name": _str(180), "files": {"type": "array", "items": _str(1000), "maxItems": 500}}, ["name", "files"]), lambda name, files: {"path": v5.artifacts.bundle(name, files)}, PermissionLevel.SYSTEM_ACTION))

    # Sandbox + capability learning -----------------------------------------------------------
    add(Tool("v5_sandbox_status", "Show sandbox execution availability without running code.", _schema(), lambda: {"docker_available": v5.sandbox.docker_available, "local_fallback_enabled": bool(v5.sandbox.allow_local_fallback)}, PermissionLevel.READ))
    add(Tool("v5_sandbox_python", "Run bounded Python and tests in the isolated sandbox. Docker has no network; local fallback is opt-in only.", _schema({"source": {"type": "string", "minLength": 1, "maxLength": 200000}, "tests": _str(200000), "timeout": {"type": "integer", "minimum": 1, "maximum": 300}}, ["source"]), lambda source, tests="", timeout=60: v5.sandbox.run_python(source, tests, timeout=timeout), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_capability_list", "List learned capability proposals.", _schema(), lambda: v5.capability_learning.list(), PermissionLevel.READ))
    add(Tool("v5_capability_installed", "List installed learned capabilities.", _schema(), lambda: v5.capability_learning.installed_list(), PermissionLevel.READ))
    add(Tool("v5_capability_propose", "Create a capability proposal; it is not installed or trusted yet.", _schema({"name": _str(120), "description": _str(2000), "source": _str(200000), "tests": _str(200000), "permission": {"type": "string", "enum": ["READ", "SAFE_ACTION", "SYSTEM_ACTION", "CRITICAL"]}, "version": _str(40)}, ["name", "description", "source"]), lambda name, description, source, tests="", permission="READ", version="0.1.0": asdict(v5.capability_learning.propose(name=name, description=description, source=source, tests=tests, permission=permission, version=version)), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_capability_test", "Test a capability proposal inside the sandbox before installation.", _schema({"proposal_id": _str(120)}, ["proposal_id"]), lambda proposal_id: asdict(v5.capability_learning.test(proposal_id, v5.sandbox.run_python)), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_capability_install", "Install a tested capability proposal after critical approval.", _schema({"proposal_id": _str(120)}, ["proposal_id"]), lambda proposal_id: {"path": str(v5.capability_learning.approve_install(proposal_id, approved=True))}, PermissionLevel.CRITICAL))
    add(Tool("v5_capability_uninstall", "Uninstall a learned capability after critical approval.", _schema({"name": _str(120), "version": _str(40)}, ["name", "version"]), lambda name, version: (v5.capability_learning.uninstall(name, version, approved=True) or {"uninstalled": f"{name}@{version}"}), PermissionLevel.CRITICAL))

    # Self-healing / research / debate / routing ---------------------------------------------
    add(Tool("v5_recovery_stats", "Show self-healing strategies, success/failure counts and scores.", _schema(), lambda: v5.self_healing.stats(), PermissionLevel.READ))
    add(Tool("v5_research_start", "Start an autonomous read-only research project through the multi-agent orchestrator.", _schema({"question": {"type": "string", "minLength": 1, "maxLength": 12000}}, ["question"]), lambda question: v5.start_research_project(question), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_debate_start", "Start proposer/challenger/tester/coordinator review before execution.", _schema({"objective": {"type": "string", "minLength": 1, "maxLength": 12000}}, ["objective"]), lambda objective: v5.start_debate_review(objective), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_resource_route", "Choose a resource/provider using latency, failures, quality and local resource constraints.", _schema({"providers": {"type": "array", "items": _obj(), "maxItems": 100}, "difficulty": {"type": "string", "enum": ["easy", "normal", "hard", "expert"]}, "prefer_local": {"type": "boolean"}, "resources": _obj()}, ["providers"]), lambda providers, difficulty="normal", prefer_local=False, resources=None: v5.resource_router.choose(providers, difficulty=difficulty, prefer_local=prefer_local, resources=ResourceSnapshot(**{k: v for k, v in (resources or {}).items() if k in ResourceSnapshot.__dataclass_fields__})), PermissionLevel.READ))

    # Signed skills --------------------------------------------------------------------------
    add(Tool("v5_skill_list", "List installed signed skills.", _schema(), lambda: v5.skills.list(), PermissionLevel.READ))
    add(Tool("v5_skill_verify", "Re-verify the installed skill manifest, signature and every package file hash.", _schema({"skill_id": _str(120), "version": _str(80)}, ["skill_id", "version"]), lambda skill_id, version: v5.skills.verify_installed(skill_id, version), PermissionLevel.READ))
    add(Tool("v5_skill_install", "Install an Ed25519-signed skill whose signature covers its manifest and every package file.", _schema({"manifest": _obj(), "files": {"type": "object", "additionalProperties": _str(300000)}, "signature_b64": _str(10000), "public_key_b64": _str(10000)}, ["manifest", "files", "signature_b64", "public_key_b64"]), lambda manifest, files, signature_b64, public_key_b64: {"path": v5.skills.install(SkillManifest(**manifest), files, signature_b64=signature_b64, public_key_b64=public_key_b64, approved=True)}, PermissionLevel.CRITICAL))
    add(Tool("v5_skill_uninstall", "Remove an installed signed skill after critical approval.", _schema({"skill_id": _str(120), "version": _str(80)}, ["skill_id", "version"]), lambda skill_id, version: (v5.skills.uninstall(skill_id, version, approved=True) or {"uninstalled": f"{skill_id}@{version}"}), PermissionLevel.CRITICAL))

    # Profiles + encrypted sync --------------------------------------------------------------
    add(Tool("v5_profile_list", "List multi-user profiles and permission namespaces.", _schema(), lambda: v5.profiles.list(), PermissionLevel.READ))
    add(Tool("v5_profile_create", "Create a local multi-user profile.", _schema({"name": {"type": "string", "minLength": 1, "maxLength": 160}, "permissions": {"type": "array", "items": _str(160), "maxItems": 128}}, ["name"]), lambda name, permissions=None: v5.profiles.create(name, permissions or []), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_profile_update", "Update a profile's name, permissions or enabled state.", _schema({"profile_id": _str(100), "name": _str(160), "permissions": {"type": "array", "items": _str(160), "maxItems": 128}, "enabled": {"type": "boolean"}}, ["profile_id"]), lambda profile_id, name="", permissions=None, enabled=None: v5.profiles.update(profile_id, name=name or None, permissions=permissions, enabled=enabled), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_profile_sync_export", "Export a profile + memory namespace as end-to-end encrypted ciphertext using a vault key reference.", _schema({"profile_id": _str(100), "key_ref": _str(160)}, ["profile_id", "key_ref"]), lambda profile_id, key_ref: v5.export_profile_sync(profile_id, key_ref), PermissionLevel.SYSTEM_ACTION))
    add(Tool("v5_profile_sync_import", "Import an encrypted profile bundle after critical approval; the key is resolved only from the vault.", _schema({"bundle_b64": {"type": "string", "minLength": 1, "maxLength": 5000000}, "key_ref": _str(160)}, ["bundle_b64", "key_ref"]), lambda bundle_b64, key_ref: v5.import_profile_sync(bundle_b64, key_ref, approved=True), PermissionLevel.CRITICAL))

    # Home/local network adapters ------------------------------------------------------------
    add(Tool("v5_home_adapter_list", "List configured home/local-network adapters and declared actions.", _schema(), lambda: v5.home_network.list(), PermissionLevel.READ))
    add(Tool("v5_home_status", "Read status from an explicitly allowlisted local-network JSON endpoint; no scanning or discovery.", _schema({"adapter": {"type": "string", "enum": ["http-json", "https-json"]}, "host": _str(255), "path": _str(1000)}, ["adapter", "host"]), lambda adapter, host, path="/status": v5.home_network.invoke(adapter, "status", host=host, path=path), PermissionLevel.READ))
    add(Tool("v5_home_command", "Send a bounded command to an explicitly allowlisted home/local-network endpoint after approval.", _schema({"adapter": {"type": "string", "enum": ["http-json", "https-json"]}, "host": _str(255), "path": _str(1000), "payload": _obj()}, ["adapter", "host"]), lambda adapter, host, path="/command", payload=None: v5.home_network.invoke(adapter, "command", host=host, path=path, payload=payload or {}, approval=lambda _n, _a: True), PermissionLevel.SYSTEM_ACTION))

    # Rollback + audit -----------------------------------------------------------------------
    add(Tool("v5_rollback_list", "List rollback timeline checkpoints.", _schema({"project_root": _str(1000)}), lambda project_root="": v5.rollback.list(project_root or None), PermissionLevel.READ))
    add(Tool("v5_rollback_capture", "Capture a Git rollback timeline checkpoint before a project change.", _schema({"project_root": {"type": "string", "minLength": 1, "maxLength": 1000}, "label": _str(160)}, ["project_root"]), lambda project_root, label="checkpoint": v5.rollback.capture(project_root, label), PermissionLevel.SAFE_ACTION))
    add(Tool("v5_rollback_preview", "Preview the effect and safety state of a rollback checkpoint.", _schema({"checkpoint_id": _str(100)}, ["checkpoint_id"]), lambda checkpoint_id: v5.rollback.preview(checkpoint_id), PermissionLevel.READ))
    add(Tool("v5_rollback_restore", "Restore tracked files to a recorded checkpoint; untracked files are preserved.", _schema({"checkpoint_id": _str(100), "approved": {"type": "boolean"}}, ["checkpoint_id", "approved"]), lambda checkpoint_id, approved: v5.rollback.restore_tracked(checkpoint_id, approved=approved), PermissionLevel.CRITICAL))
    add(Tool("v5_audit_summary", "Summarize recent IRAS activity/audit traces.", _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 2000}}), lambda limit=500: v5.audit.summary(limit), PermissionLevel.READ))
    add(Tool("v5_audit_rows", "Read bounded recent activity/audit rows.", _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 2000}, "operation": _str(200), "errors_only": {"type": "boolean"}}), lambda limit=500, operation="", errors_only=False: v5.audit.rows(limit, operation=operation, errors_only=errors_only), PermissionLevel.READ))
    return t


def _build_graph(v5, root: str):
    graph = ProjectKnowledgeGraph(root)
    summary = graph.build()
    out = v5.state_dir / "knowledge"
    out.mkdir(parents=True, exist_ok=True)
    path = out / (Path(root).name + ".json")
    graph.export(path)
    return {**summary, "snapshot": str(path)}


def _browser_start(v5, headless: bool, profile: str):
    v5.browser.start(headless=bool(headless), profile=profile or "default")
    return {"started": True, "tabs": v5.browser.tabs()}


def _browser_navigate_with_heal(v5, url: str, tab_id: str | None):
    try:
        return v5.browser.navigate(url, tab_id=tab_id).__dict__
    except Exception as first:
        recovery = v5.self_healing.recover(first, {"browser_restart": lambda: (v5.browser.stop(), v5.browser.start(headless=True))})
        if not recovery.get("recovered"):
            raise
        return {**v5.browser.navigate(url, tab_id=None).__dict__, "recovery": recovery}


def _voice_status(v5):
    return {
        "running": bool(v5.voice.running),
        "speaking": bool(v5.voice.speaking),
        "wake_words": list(v5.voice.wake_words),
        "require_wake_word": bool(v5.voice.require_wake_word),
        "turn_count": len(v5.voice.turns),
    }
