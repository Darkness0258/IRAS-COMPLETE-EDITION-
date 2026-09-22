from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import shutil
import time
from typing import Any, Callable

from .common import EventBus, SQLiteDB, new_id, utc_now
from .scheduler import PersistentScheduler
from .automation_engine import AutomationEngine
from .cognitive_core import CognitiveCore
from .strengthening_core import RC8StrengtheningCore
from .monitoring import ProactiveMonitor, MonitorResult
from .visual_agent import AdvancedVisualAgent
from .browser_agent import DedicatedBrowserAgent
from .workflow import WorkflowRecorder
from .semantic_memory import SemanticMemory
from .knowledge_graph import ProjectKnowledgeGraph
from .coding_workspace import CodingWorkspaceManager
from .self_healing import SelfHealingEngine, RecoveryStrategy
from .capability_learning import CapabilityLearner
from .connectors import ConnectorRegistry
from .voice_runtime import FullDuplexVoiceRuntime
from .mobile import MobileCompanionHub
from .notifications import NotificationCenter
from .artifacts import ArtifactEngine
from .vault import SecretVault
from .sandbox import SandboxRunner
from .research import AutonomousResearchEngine
from .debate import AgentDebate
from .resource_router import ResourceAwareRouter
from .rollback import RollbackTimeline
from .audit_dashboard import AuditDashboard
from .skills import SkillMarketplace
from .home_network import HomeNetworkHub, HttpJsonHomeAdapter
from .profiles import ProfileStore
from .encrypted_sync import EncryptedSync
from .goals import GoalHierarchy
from .migrations import MigrationManager


FEATURES = (
    "persistent_scheduled_autonomy",
    "proactive_monitoring",
    "advanced_visual_computer_agent",
    "managed_vision_runtime",
    "dedicated_browser_agent",
    "workflow_recording",
    "long_term_semantic_memory",
    "project_knowledge_graph",
    "isolated_coding_workspaces",
    "self_healing_workflows",
    "capability_learning",
    "plugin_connector_layer",
    "full_duplex_voice_runtime",
    "mobile_companion_hub",
    "android_companion",
    "notification_system",
    "artifact_engine",
    "secure_secrets_vault",
    "sandbox_execution",
    "autonomous_research_projects",
    "dedicated_web_research_agent",
    "permissioned_software_installer_agent",
    "agent_debate_review",
    "resource_aware_intelligence",
    "rollback_timeline",
    "activity_audit_dashboard",
    "signed_skill_marketplace",
    "home_network_adapters",
    "multi_user_profiles",
    "encrypted_sync",
    "goal_hierarchy",
    "schema_migrations",
    "control_center_ui",
    "unified_cloud_workspace",
    "master_control",
    "release_engineering",
)


class V5Runtime:
    """IRAS v5 autonomous operating layer over the v4.4 enforcement core."""

    def __init__(
        self,
        state_dir: str | Path | None = None,
        *,
        database_url: str = "",
        trace_path: str | Path | None = None,
        orchestration_manager: Any = None,
    ):
        self.state_dir = Path(state_dir or (Path.home() / ".iras" / "v5")).expanduser()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.bus = EventBus()
        self.db = SQLiteDB(self.state_dir / "state.db", database_url=database_url)
        self.scheduler = PersistentScheduler(self.db, self.bus)
        self.automations = AutomationEngine(self.db, self.bus)
        self.monitoring = ProactiveMonitor(self.db, self.bus)
        self.visual = AdvancedVisualAgent()
        self.browser = DedicatedBrowserAgent(self.state_dir / "browser")
        self.workflows = WorkflowRecorder(self.state_dir / "workflows")
        self.semantic_memory = SemanticMemory(self.db)
        self.workspace_manager = CodingWorkspaceManager(self.state_dir / "worktrees")
        self.self_healing = SelfHealingEngine(self.db, self.bus)
        self.capability_learning = CapabilityLearner(self.state_dir / "capabilities")
        self.vault = SecretVault(self.state_dir / "vault.json")
        self.connectors = ConnectorRegistry(self.db, self.vault)
        self.voice = FullDuplexVoiceRuntime()
        self.mobile = MobileCompanionHub(self.db)
        self.notifications = NotificationCenter(self.db, self.bus)
        self.artifacts = ArtifactEngine(self.state_dir / "artifacts")
        self.sandbox = SandboxRunner(
            allow_local_fallback=str(os.getenv("IRAS_V5_SANDBOX_LOCAL_FALLBACK", "false")).lower()
            in {"1", "true", "yes", "on"}
        )
        self.research = AutonomousResearchEngine()
        self.debate = AgentDebate()
        self.resource_router = ResourceAwareRouter()
        self.rollback = RollbackTimeline(self.db)
        self.audit = AuditDashboard(trace_path or (Path.home() / ".iras" / "traces.jsonl"))
        self.skills = SkillMarketplace(self.state_dir / "skills")
        networks = [x.strip() for x in os.getenv("IRAS_HOME_NETWORKS", "127.0.0.0/8").split(",") if x.strip()]
        self.home_network = HomeNetworkHub(networks)
        self.home_network.register("http-json", HttpJsonHomeAdapter(use_https=False))
        self.home_network.register("https-json", HttpJsonHomeAdapter(use_https=True))
        self.profiles = ProfileStore(self.db)
        self.sync = EncryptedSync()
        self.goals = GoalHierarchy(self.db)
        self.cognition = CognitiveCore(self.db, self.bus)
        self.cognition.bind_goal_provider(lambda: self.goals.next_actions(20))
        self.strengthening = RC8StrengtheningCore(self.db, self.bus)
        self.strengthening.context.bind_memory_provider(lambda query, limit: self.cognition.recall(query, limit=limit, hops=2))
        self.strengthening.interop.bind_secret_resolver(self.vault.get)
        self.migrations = MigrationManager(self.db)
        self.migrations.apply_all()
        self.orchestration_manager = orchestration_manager
        self._tool_executor: Callable[[str, dict[str, Any]], Any] | None = None
        self._started = False
        self._register_builtin_monitors()
        self._register_builtin_recovery()
        self._wire_events()

    @property
    def persistent_backend(self) -> str:
        return "postgres" if self.db.database_url else "sqlite"

    def bind_tool_executor(self, executor: Callable[[str, dict[str, Any]], Any]) -> None:
        """Bind ToolRegistry.execute so workflows and automations re-enter permission gates."""
        self._tool_executor = executor
        self.automations.bind_executor(self.execute_automation)

    def bind_automation_authorizer(self, checker: Callable[[dict[str, Any]], bool] | None) -> None:
        self.automations.bind_unattended_authorizer(checker)

    def _wire_events(self) -> None:
        self.bus.subscribe("monitor.changed", self._notify_monitor_change)
        self.bus.subscribe("monitor.error", self._notify_monitor_error)
        self.bus.subscribe("automation.finished", self._learn_automation_outcome)
        self.notifications.register_channel(
            "mobile",
            lambda n: self.mobile.push_event(
                "notification",
                {
                    "notification_id": n.notification_id,
                    "title": n.title,
                    "body": n.body,
                    "severity": n.severity,
                },
            ),
        )

    def _register_builtin_monitors(self) -> None:
        def disk(config: dict[str, Any]) -> MonitorResult:
            path = str(config.get("path") or self.state_dir)
            usage = shutil.disk_usage(path)
            free_gb = round(usage.free / (1024**3), 2)
            threshold = float(config.get("min_free_gb") or 5)
            return MonitorResult(
                {"free_gb": free_gb, "total_gb": round(usage.total / (1024**3), 2)},
                free_gb >= threshold,
                f"{free_gb} GB free on {path}",
            )

        def http(config: dict[str, Any]) -> MonitorResult:
            import httpx

            url = str(config.get("url") or "")
            if not url.startswith("https://"):
                raise ValueError("Proactive HTTP monitors require HTTPS.")
            started = time.perf_counter()
            r = httpx.get(url, timeout=float(config.get("timeout") or 10), follow_redirects=True)
            latency = int((time.perf_counter() - started) * 1000)
            expected = int(config.get("status") or 200)
            return MonitorResult(
                {"status": r.status_code, "latency_ms": latency, "etag": r.headers.get("etag", "")},
                r.status_code == expected,
                f"HTTP {r.status_code} in {latency}ms",
            )

        self.monitoring.register_checker("disk", disk)
        self.monitoring.register_checker("website", http)
        self.monitoring.register_checker("api", http)

    def _register_builtin_recovery(self) -> None:
        def call(name: str):
            def handler(ctx: dict[str, Any]):
                fn = ctx.get(name)
                if not callable(fn):
                    raise RuntimeError(f"Recovery callback unavailable: {name}")
                return fn()
            return handler

        self.self_healing.register(RecoveryStrategy("provider-fallback", "provider", call("provider_fallback"), 2))
        self.self_healing.register(RecoveryStrategy("browser-restart", "browser", call("browser_restart"), 1))
        self.self_healing.register(RecoveryStrategy("device-reconnect", "device", call("device_reconnect"), 2))
        self.self_healing.register(RecoveryStrategy("test-retry", "test", call("test_retry"), 1))

    def _notify_monitor_change(self, event) -> None:
        payload = event.payload
        severity = "warning" if not payload.get("healthy", True) else "info"
        self.notifications.notify(
            f"Monitor changed: {payload.get('name')}",
            str(payload.get("summary") or "A monitored condition changed."),
            severity=severity,
            channel="browser",
        )
        self.mobile.push_event("monitor.changed", payload)

    def _notify_monitor_error(self, event) -> None:
        payload = event.payload
        self.notifications.notify(
            f"Monitor error: {payload.get('name')}",
            str(payload.get("error") or "Monitor execution failed."),
            severity="error",
            channel="mobile",
        )

    def _learn_automation_outcome(self, event) -> None:
        payload = dict(getattr(event, "payload", {}) or {})
        automation_id = str(payload.get("automation_id") or "unknown")
        ok = bool(payload.get("ok"))
        source = str(payload.get("source") or "automation")
        error = str(payload.get("error") or "").strip()
        summary = f"Automation {automation_id} {'succeeded' if ok else 'failed'} via {source}."
        if error:
            summary += " Error: " + error[:1500]
        try:
            self.cognition.learn_outcome(summary, success=ok, source="automation")
        except Exception:
            pass

    def submit_scheduled_prompt(self, prompt: str, row: dict[str, Any]) -> Any:
        if self.orchestration_manager is None:
            raise RuntimeError("No orchestration manager is attached to v5 scheduled autonomy.")
        return self.orchestration_manager.submit_objective(
            prompt,
            context={
                "scheduled": True,
                "scheduled_permission": "read_only",
                "schedule_id": row.get("job_id"),
            },
            requester_device="v5-scheduler",
        )

    def execute_automation(self, row: dict[str, Any], trigger_payload: dict[str, Any]) -> Any:
        action_kind = str(row.get("action_kind") or "prompt").strip().lower()
        if action_kind == "workflow":
            workflow_id = str(row.get("action_ref") or "").strip()
            if not workflow_id:
                raise ValueError("Automation workflow id is missing.")
            return self.replay_workflow(workflow_id)
        if self.orchestration_manager is None:
            raise RuntimeError("No orchestration manager is attached to automation execution.")
        prompt = str(row.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("Automation prompt is empty.")
        context = {
            "automation": True,
            "automation_id": row.get("automation_id"),
            "automation_permission": str(row.get("permission_mode") or "read_only"),
            "automation_trigger": dict(trigger_payload or {}),
        }
        run = self.orchestration_manager.submit_objective(
            prompt,
            context=context,
            requester_device="v5-automation",
        )
        run_id = str((run or {}).get("run_id") or "")
        if not run_id:
            return run
        try:
            timeout = int(os.getenv("IRAS_V5_AUTOMATION_WAIT_SECONDS", "1800"))
        except ValueError:
            timeout = 1800
        finished = self.orchestration_manager.wait(run_id, timeout=max(30, min(timeout, 21600)))
        status = str((finished or {}).get("status") or "").lower()
        if status in {"failed", "cancelled", "blocked", "interrupted"}:
            raise RuntimeError(str((finished or {}).get("error") or f"Automation orchestration ended as {status}."))
        return finished

    def start_research_project(self, question: str) -> dict[str, Any]:
        if self.orchestration_manager is None:
            raise RuntimeError("Autonomous research requires the multi-agent orchestration manager.")
        return self.orchestration_manager.submit_objective(
            str(question),
            context={"v5_mode": "research", "research_project": True, "default_permission": "read_only"},
            requester_device="v5-research",
        )

    def start_debate_review(self, objective: str) -> dict[str, Any]:
        if self.orchestration_manager is None:
            raise RuntimeError("Agent debate requires the multi-agent orchestration manager.")
        return self.orchestration_manager.submit_objective(
            "Debate and review this objective before recommending execution: " + str(objective),
            context={"v5_mode": "debate", "debate_review": True, "default_permission": "read_only"},
            requester_device="v5-debate",
        )

    def replay_workflow(self, workflow_id: str) -> list[Any]:
        if self._tool_executor is None:
            raise RuntimeError("Workflow replay is not bound to the permissioned ToolRegistry.")

        def execute(action: str, arguments: dict[str, Any]) -> Any:
            result = self._tool_executor(action, arguments)
            ok = bool(getattr(result, "ok", False))
            if not ok:
                raise RuntimeError(str(getattr(result, "error", "Workflow tool execution failed.")))
            return getattr(result, "output", result)

        return self.workflows.replay(workflow_id, execute)

    def export_profile_sync(self, profile_id: str, key_secret_ref: str) -> dict[str, Any]:
        profile = self.profiles.get(profile_id)
        if not profile:
            raise KeyError(profile_id)
        key = self.vault.get(key_secret_ref)
        payload = {
            "format": "iras-profile-sync-v1",
            "profile": profile,
            "memories": self.semantic_memory.export_namespace(profile["memory_namespace"]),
            "exported_at": utc_now(),
        }
        blob = self.sync.encrypt(payload, key)
        digest = hashlib.sha256(blob).hexdigest()
        sync_id = new_id("sync_")
        self.db.execute(
            "INSERT INTO v5_sync_journal(sync_id,profile_id,direction,bundle_sha256,created_at,status) VALUES(?,?,?,?,?,?)",
            (sync_id, profile_id, "export", digest, utc_now(), "complete"),
        )
        return {"sync_id": sync_id, "profile_id": profile_id, "bundle_base64": base64.b64encode(blob).decode("ascii"), "sha256": digest}

    def import_profile_sync(self, bundle_base64: str, key_secret_ref: str, *, approved: bool = False) -> dict[str, Any]:
        if not approved:
            raise PermissionError("Profile sync import requires explicit approval.")
        blob = base64.b64decode(bundle_base64, validate=True)
        key = self.vault.get(key_secret_ref)
        payload = self.sync.decrypt(blob, key)
        if payload.get("format") != "iras-profile-sync-v1" or not isinstance(payload.get("profile"), dict):
            raise ValueError("Invalid IRAS profile sync bundle.")
        profile = self.profiles.upsert_snapshot(payload["profile"])
        count = self.semantic_memory.import_rows(list(payload.get("memories") or []), namespace=profile["memory_namespace"])
        digest = hashlib.sha256(blob).hexdigest()
        sync_id = new_id("sync_")
        self.db.execute(
            "INSERT INTO v5_sync_journal(sync_id,profile_id,direction,bundle_sha256,created_at,status) VALUES(?,?,?,?,?,?)",
            (sync_id, profile["profile_id"], "import", digest, utc_now(), "complete"),
        )
        return {"sync_id": sync_id, "profile": profile, "memories_imported": count, "sha256": digest}

    def start_services(self) -> None:
        if self._started:
            return
        if self.orchestration_manager is not None:
            self.scheduler.start(
                self.submit_scheduled_prompt,
                poll_seconds=5.0,
                max_workers=int(os.getenv("IRAS_V5_SCHEDULER_WORKERS", "4")),
            )
        if self._tool_executor is not None:
            self.automations.start(
                poll_seconds=float(os.getenv("IRAS_V5_AUTOMATION_POLL_SECONDS", "2")),
                max_workers=int(os.getenv("IRAS_V5_AUTOMATION_WORKERS", "4")),
            )
        self.cognition.start(
            interval_seconds=float(os.getenv("IRAS_V5_COGNITION_TICK_SECONDS", "10"))
        )
        self.monitoring.start(poll_seconds=float(os.getenv("IRAS_V5_MONITOR_POLL_SECONDS", "15")))
        self._started = True
        self.bus.publish("v5.started", version="5.0.0-rc5")

    def stop_services(self) -> None:
        self.scheduler.stop()
        self.automations.stop()
        self.cognition.stop()
        self.monitoring.stop()
        self.voice.stop()
        try:
            self.browser.stop()
        except Exception:
            pass
        self._started = False
        self.bus.publish("v5.stopped", version="5.0.0-rc5")

    def start_scheduled_autonomy(self) -> None:
        self.start_services()

    def feature_status(self) -> list[dict[str, Any]]:
        migration = self.migrations.status()
        operational = {
            "persistent_scheduled_autonomy": self.orchestration_manager is not None,
            "proactive_monitoring": True,
            "advanced_visual_computer_agent": True,
            "managed_vision_runtime": True,
            "dedicated_browser_agent": self.browser.available,
            "workflow_recording": True,
            "long_term_semantic_memory": True,
            "project_knowledge_graph": True,
            "isolated_coding_workspaces": shutil.which("git") is not None,
            "self_healing_workflows": True,
            "capability_learning": True,
            "plugin_connector_layer": True,
            "full_duplex_voice_runtime": True,
            "mobile_companion_hub": True,
            "android_companion": True,
            "notification_system": True,
            "artifact_engine": True,
            "secure_secrets_vault": self.vault.backend != "locked-no-master-key",
            "sandbox_execution": self.sandbox.docker_available or self.sandbox.allow_local_fallback,
            "autonomous_research_projects": self.orchestration_manager is not None,
            "agent_debate_review": self.orchestration_manager is not None,
            "resource_aware_intelligence": True,
            "rollback_timeline": shutil.which("git") is not None,
            "activity_audit_dashboard": True,
            "signed_skill_marketplace": True,
            "home_network_adapters": bool(self.home_network.adapters),
            "multi_user_profiles": True,
            "encrypted_sync": self.vault.backend != "locked-no-master-key",
            "goal_hierarchy": True,
            "schema_migrations": bool(migration.get("complete")),
            "control_center_ui": True,
            "unified_cloud_workspace": True,
            "master_control": True,
            "release_engineering": True,
        }
        return [{"feature": name, "operational": bool(operational.get(name, False))} for name in FEATURES]

    def status(self) -> dict[str, Any]:
        feature_status = self.feature_status()
        return {
            "version": "5.0.0-rc5",
            "features": list(FEATURES),
            "feature_count": len(FEATURES),
            "feature_status": feature_status,
            "operational_features": sum(1 for x in feature_status if x["operational"]),
            "persistent_backend": self.persistent_backend,
            "services_started": self._started,
            "scheduler_worker_active": bool(self._started and self.orchestration_manager is not None),
            "browser_available": self.browser.available,
            "browser_running": bool(getattr(self.browser, "_context", None)),
            "docker_sandbox_available": self.sandbox.docker_available,
            "sandbox_local_fallback": self.sandbox.allow_local_fallback,
            "vault_backend": self.vault.backend,
            "connected_connectors": [x["connector_id"] for x in self.connectors.list() if x["connected"]],
            "connector_credentials_ready": [x["connector_id"] for x in self.connectors.list() if x.get("credentials", {}).get("ready")],
            "scheduled_jobs": len(self.scheduler.list()),
            "automations": len(self.automations.list()),
            "automation_worker_active": self.automations.running,
            "cognitive_core": self.cognition.status(),
            "cognitive_core_running": self.cognition.running,
            "rc8_strengthening": self.strengthening.status(),
            "monitors": len(self.monitoring.list()),
            "unread_notifications": len(self.notifications.list(unread_only=True)),
            "mobile_devices": len(self.mobile.list_devices()),
            "coding_workspaces": len(self.workspace_manager.list()),
            "voice_running": self.voice.running,
            "migrations": self.migrations.status(),
            "home_adapters": self.home_network.list(),
            "build_mode": "offline-safe",
            "remote_protocol": 1,
        }


def build_v5_runtime(
    *, orchestration_manager: Any = None, state_dir: str | Path | None = None,
    database_url: str | None = None, trace_path: str | Path | None = None,
) -> V5Runtime:
    return V5Runtime(
        state_dir,
        database_url=str(database_url if database_url is not None else os.getenv("DATABASE_URL", "")),
        trace_path=trace_path,
        orchestration_manager=orchestration_manager,
    )
