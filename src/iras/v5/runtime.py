from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import time
from typing import Any, Callable

from .common import SQLiteDB, EventBus
from .scheduler import PersistentScheduler
from .monitoring import ProactiveMonitor, MonitorResult
from .visual_agent import AdvancedVisualAgent
from .browser_agent import DedicatedBrowserAgent
from .workflow import WorkflowRecorder
from .semantic_memory import SemanticMemory
from .knowledge_graph import ProjectKnowledgeGraph
from .coding_workspace import CodingWorkspaceManager
from .self_healing import SelfHealingEngine
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
from .home_network import HomeNetworkHub
from .profiles import ProfileStore
from .encrypted_sync import EncryptedSync
from .goals import GoalHierarchy


FEATURES = (
    "persistent_scheduled_autonomy",
    "proactive_monitoring",
    "advanced_visual_computer_agent",
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
    "notification_system",
    "artifact_engine",
    "secure_secrets_vault",
    "sandbox_execution",
    "autonomous_research_projects",
    "agent_debate_review",
    "resource_aware_intelligence",
    "rollback_timeline",
    "activity_audit_dashboard",
    "signed_skill_marketplace",
    "home_network_adapters",
    "multi_user_profiles",
    "encrypted_sync",
    "goal_hierarchy",
)


class V5Runtime:
    """High-level IRAS v5 capability runtime.

    The v4.4 agent/device bridge remains the enforcement layer for computer
    control. v5 adds durable organization and orchestration around it.
    """

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
        self.monitoring = ProactiveMonitor(self.db, self.bus)
        self.visual = AdvancedVisualAgent()
        self.browser = DedicatedBrowserAgent(self.state_dir / "browser")
        self.workflows = WorkflowRecorder(self.state_dir / "workflows")
        self.semantic_memory = SemanticMemory(self.db)
        self.workspace_manager = CodingWorkspaceManager(self.state_dir / "worktrees")
        self.self_healing = SelfHealingEngine(self.db, self.bus)
        self.capability_learning = CapabilityLearner(self.state_dir / "capabilities")
        self.connectors = ConnectorRegistry()
        self.voice = FullDuplexVoiceRuntime()
        self.mobile = MobileCompanionHub(self.db)
        self.notifications = NotificationCenter(self.db, self.bus)
        self.artifacts = ArtifactEngine(self.state_dir / "artifacts")
        self.vault = SecretVault(self.state_dir / "vault.json")
        self.sandbox = SandboxRunner()
        self.research = AutonomousResearchEngine()
        self.debate = AgentDebate()
        self.resource_router = ResourceAwareRouter()
        self.rollback = RollbackTimeline(self.db)
        self.audit = AuditDashboard(trace_path or (Path.home() / ".iras" / "traces.jsonl"))
        self.skills = SkillMarketplace(self.state_dir / "skills")
        self.home_network = HomeNetworkHub()
        self.profiles = ProfileStore(self.db)
        self.sync = EncryptedSync()
        self.goals = GoalHierarchy(self.db)
        self.orchestration_manager = orchestration_manager
        self._register_builtin_monitors()
        self.bus.subscribe("monitor.changed", self._notify_monitor_change)

    @property
    def persistent_backend(self) -> str:
        return "postgres" if self.db.database_url else "sqlite"

    def _register_builtin_monitors(self) -> None:
        def disk(config: dict[str, Any]) -> MonitorResult:
            path = str(config.get("path") or self.state_dir)
            usage = shutil.disk_usage(path)
            free_gb = round(usage.free / (1024 ** 3), 2)
            threshold = float(config.get("min_free_gb") or 5)
            return MonitorResult({"free_gb": free_gb, "total_gb": round(usage.total / (1024 ** 3), 2)}, free_gb >= threshold,
                                 f"{free_gb} GB free on {path}")

        def http(config: dict[str, Any]) -> MonitorResult:
            import httpx
            url = str(config.get("url") or "")
            if not url.startswith("https://"):
                raise ValueError("Proactive HTTP monitors require HTTPS.")
            started = time.perf_counter()
            r = httpx.get(url, timeout=float(config.get("timeout") or 10), follow_redirects=True)
            latency = int((time.perf_counter() - started) * 1000)
            expected = int(config.get("status") or 200)
            return MonitorResult({"status": r.status_code, "latency_ms": latency, "etag": r.headers.get("etag", "")}, r.status_code == expected,
                                 f"HTTP {r.status_code} in {latency}ms")

        self.monitoring.register_checker("disk", disk)
        self.monitoring.register_checker("website", http)
        self.monitoring.register_checker("api", http)

    def _notify_monitor_change(self, event) -> None:
        payload = event.payload
        severity = "warning" if not payload.get("healthy", True) else "info"
        self.notifications.notify(
            f"Monitor changed: {payload.get('name')}",
            str(payload.get("summary") or "A monitored condition changed."),
            severity=severity,
            channel="browser",
        )

    def submit_scheduled_prompt(self, prompt: str, row: dict[str, Any]) -> Any:
        if self.orchestration_manager is None:
            raise RuntimeError("No orchestration manager is attached to v5 scheduled autonomy.")
        return self.orchestration_manager.submit_objective(
            prompt,
            context={"scheduled": True, "scheduled_permission": "read_only", "schedule_id": row.get("job_id")},
            requester_device="v5-scheduler",
        )

    def start_scheduled_autonomy(self) -> None:
        if self.orchestration_manager is None:
            return
        self.scheduler.start(self.submit_scheduled_prompt, poll_seconds=5.0)

    def status(self) -> dict[str, Any]:
        return {
            "version": "5.0.0-rc2",
            "features": list(FEATURES),
            "feature_count": len(FEATURES),
            "persistent_backend": self.persistent_backend,
            "browser_available": self.browser.available,
            "docker_sandbox_available": self.sandbox.docker_available,
            "connected_connectors": [x["connector_id"] for x in self.connectors.list() if x["connected"]],
            "scheduled_jobs": len(self.scheduler.list()),
            "monitors": len(self.monitoring.list()),
            "unread_notifications": len(self.notifications.list(unread_only=True)),
        }


def build_v5_runtime(*, orchestration_manager: Any = None, state_dir: str | Path | None = None,
                     database_url: str | None = None, trace_path: str | Path | None = None) -> V5Runtime:
    return V5Runtime(
        state_dir,
        database_url=str(database_url if database_url is not None else os.getenv("DATABASE_URL", "")),
        trace_path=trace_path,
        orchestration_manager=orchestration_manager,
    )
