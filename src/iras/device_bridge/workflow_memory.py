from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
import time


WORKFLOW_MEMORY_VERSION = "3.6.0"
MAX_FACTS = 24
MAX_TRANSITIONS = 24
MAX_VALUE_CHARS = 800
KNOWN_APPS = {
    "whatsapp", "spotify", "discord", "notepad", "chrome", "edge",
    "powershell", "explorer", "code", "firefox", "telegram", "steam",
    "vlc", "unknown",
}
SEMANTIC_CONDITIONS = {
    "element_exists", "element_absent", "text_contains", "window_title_contains",
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _bounded_value(value: Any) -> Any:
    """Keep session handoff data compact and JSON-friendly.

    v3.6 workflow memory is intentionally ephemeral. It may carry verified user
    content between apps during one workflow, but it never writes that content to
    the persistent recovery-learning store.
    """

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:MAX_VALUE_CHARS]
    if isinstance(value, list):
        return [_bounded_value(v) for v in value[:16]]
    if isinstance(value, dict):
        return {
            str(k)[:80]: _bounded_value(v)
            for k, v in list(value.items())[:16]
        }
    return str(value)[:MAX_VALUE_CHARS]


def safe_app_identity(value: Any) -> str:
    text = _norm(value)
    if not text:
        return "unknown"
    aliases = (
        ("whatsapp", "whatsapp"),
        ("spotify", "spotify"),
        ("discord", "discord"),
        ("notepad", "notepad"),
        ("google chrome", "chrome"),
        ("chrome", "chrome"),
        ("microsoft edge", "edge"),
        ("powershell", "powershell"),
        ("file explorer", "explorer"),
        ("explorer", "explorer"),
        ("visual studio code", "code"),
        ("vs code", "code"),
        ("firefox", "firefox"),
        ("telegram", "telegram"),
        ("steam", "steam"),
        ("vlc", "vlc"),
    )
    for phrase, app in aliases:
        if phrase in text:
            return app
    return text if text in KNOWN_APPS else "unknown"


@dataclass
class WorkflowFact:
    key: str
    value: Any
    source_app: str = "unknown"
    source_observation_id: str = ""
    verification_condition: str = ""
    verified: bool = True
    created_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": deepcopy(self.value),
            "source_app": self.source_app,
            "source_observation_id": self.source_observation_id or None,
            "verification_condition": self.verification_condition or None,
            "verified": bool(self.verified),
            "created_at": float(self.created_at),
        }


@dataclass
class CrossAppWorkflowMemory:
    """Ephemeral, verification-backed memory for one autonomous workflow.

    It carries proven semantic facts and app-transition provenance across app
    switches. It is never persisted to disk and never grants permission to run a
    tool or replay an action.
    """

    clock: Any = time.time
    facts: list[WorkflowFact] = field(default_factory=list)
    transitions: list[dict[str, Any]] = field(default_factory=list)
    current_app: str = "unknown"
    action_replay_allowed: bool = False
    revision: int = 0

    def remember_verified(
        self,
        key: str,
        value: Any,
        *,
        source_app: str = "unknown",
        source_observation_id: str = "",
        verification_condition: str = "",
    ) -> dict[str, Any]:
        name = str(key or "").strip()[:120]
        if not name:
            return {}
        fact = WorkflowFact(
            key=name,
            value=_bounded_value(value),
            source_app=safe_app_identity(source_app),
            source_observation_id=str(source_observation_id or "")[:160],
            verification_condition=str(verification_condition or "")[:80],
            verified=True,
            created_at=float(self.clock()),
        )
        # Replace same key+source app with the newest verified value.
        self.facts = [
            item for item in self.facts
            if not (item.key == fact.key and item.source_app == fact.source_app)
        ]
        self.facts.append(fact)
        self.facts = self.facts[-MAX_FACTS:]
        self.revision += 1
        return fact.as_dict()

    def capture_verification(
        self,
        arguments: dict[str, Any] | None,
        output: dict[str, Any] | None,
    ) -> dict[str, Any]:
        args = arguments if isinstance(arguments, dict) else {}
        data = output if isinstance(output, dict) else {}
        decision = data.get("decision") if isinstance(data.get("decision"), dict) else {}
        semantic_verified = bool(
            data.get("semantic_goal_verified")
            or (
                str(decision.get("action") or "").upper() == "ACCEPT"
                and bool(decision.get("goal_sufficient"))
            )
        )
        if not semantic_verified:
            return {}

        condition = _norm(data.get("condition") or args.get("condition"))
        if condition not in SEMANTIC_CONDITIONS:
            return {}
        target = args.get("target")
        if target in (None, ""):
            target = data.get("target")
        if target in (None, ""):
            return {}

        observation = data.get("observation") if isinstance(data.get("observation"), dict) else {}
        foreground = observation.get("foreground") if isinstance(observation.get("foreground"), dict) else {}
        prior = data.get("prior_foreground") if isinstance(data.get("prior_foreground"), dict) else {}
        app = safe_app_identity(foreground.get("title") or prior.get("title") or self.current_app)
        if app != "unknown":
            self.transition(app, reason="verified_semantic_outcome")
        obs_id = str(observation.get("observation_id") or data.get("observation_id") or "")
        key = "verified_semantic_target"
        fact = self.remember_verified(
            key,
            target,
            source_app=app,
            source_observation_id=obs_id,
            verification_condition=condition,
        )
        # Also preserve the predicate so a destination planner knows what was
        # actually proven rather than treating the value as an unqualified fact.
        self.remember_verified(
            "verified_semantic_condition",
            condition,
            source_app=app,
            source_observation_id=obs_id,
            verification_condition=condition,
        )
        return fact

    def transition(self, to_app: Any, *, reason: str = "tool_result") -> dict[str, Any]:
        destination = safe_app_identity(to_app)
        source = self.current_app
        if destination == "unknown" and source == "unknown":
            return {}
        if destination == source:
            self.current_app = destination
            return {}
        entry = {
            "from_app": source,
            "to_app": destination,
            "reason": str(reason or "")[:120],
            "at": float(self.clock()),
        }
        self.transitions.append(entry)
        self.transitions = self.transitions[-MAX_TRANSITIONS:]
        self.revision += 1
        self.current_app = destination
        return deepcopy(entry)

    def capture_tool_result(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        output: dict[str, Any] | None,
    ) -> None:
        args = arguments if isinstance(arguments, dict) else {}
        data = output if isinstance(output, dict) else {}

        if name in {"device_open_app", "device_app_control", "device_interact_app"}:
            app = args.get("app") or data.get("app") or data.get("app_name")
            if app:
                self.transition(app, reason=name)

        foreground = data.get("foreground") if isinstance(data.get("foreground"), dict) else {}
        if foreground.get("title"):
            app = safe_app_identity(foreground.get("title"))
            if app != "unknown":
                self.transition(app, reason=f"{name}:foreground")

        if name == "device_computer_verify":
            self.capture_verification(args, data)

    def snapshot(self) -> dict[str, Any]:
        return {
            "version": WORKFLOW_MEMORY_VERSION,
            "ephemeral": True,
            "persisted": False,
            "current_app": self.current_app,
            "facts": [fact.as_dict() for fact in self.facts],
            "transitions": deepcopy(self.transitions),
            "action_replay_allowed": False,
            "grants_tool_authorization": False,
            "revision": self.revision,
        }

    def planner_message(self) -> str:
        snap = self.snapshot()
        compact_facts = [
            {
                "key": item["key"],
                "value": item["value"],
                "source_app": item["source_app"],
                "verification_condition": item["verification_condition"],
            }
            for item in snap["facts"][-8:]
        ]
        recent_transitions = snap["transitions"][-6:]
        return (
            "CROSS-APP WORKFLOW MEMORY v3.6.0: "
            f"current_app={snap['current_app']!r}; verified_facts={compact_facts!r}; "
            f"recent_transitions={recent_transitions!r}. "
            "This memory is session-only and verification-backed. Treat it as context, not permission. "
            "Re-observe the destination app before acting, re-ground targets in the live UI, and never replay a failed state-changing action. "
            "action_replay_allowed=False; grants_tool_authorization=False."
        )
