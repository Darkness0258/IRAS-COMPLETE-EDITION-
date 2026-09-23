from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from .common import EventBus, SQLiteDB, new_id, utc_now


_ALLOWED_EVENT_KINDS = {
    "observe",
    "action",
    "verification",
    "failure",
    "repair",
    "checkpoint",
    "blocker",
    "completion",
}
_TERMINAL_STATUSES = {"completed", "blocked", "cancelled"}
_SENSITIVE_KEY_PARTS = ("password", "passwd", "secret", "token", "api_key", "apikey", "authorization", "cookie")


def _sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "[truncated]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:200]:
            name = str(key)[:240]
            lowered = name.lower().replace("-", "_")
            if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
                out[name] = "[redacted]"
            else:
                out[name] = _sanitize(item, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, depth=depth + 1) for item in list(value)[:500]]
    if isinstance(value, str):
        return value[:12000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:12000]


def _json(value: Any) -> str:
    return json.dumps(_sanitize(value if value is not None else {}), ensure_ascii=False, sort_keys=True, default=str)


def _load(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 4)


def _age_seconds(timestamp: str | None) -> float | None:
    if not timestamp:
        return None
    try:
        then = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - then.astimezone(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


class GoalContinuityEngine:
    """Persistent goal/evidence ledger for safe interruption and restart continuity.

    The ledger never executes tools and never replays side effects. It only records
    bounded evidence/action summaries and recommends what class of step should happen
    next. Permission enforcement remains in the existing IRAS tool/remote layers.
    """

    def __init__(self, db: SQLiteDB, bus: EventBus | None = None):
        self.db = db
        self.bus = bus or EventBus()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        for sql in (
            """CREATE TABLE IF NOT EXISTS v5_goal_continuity_runs(
                run_id TEXT PRIMARY KEY,
                run_key TEXT,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                phase TEXT NOT NULL,
                confidence REAL NOT NULL,
                revision INTEGER NOT NULL DEFAULT 0,
                world_fingerprint TEXT,
                last_observed_at TEXT,
                last_verified_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS v5_goal_continuity_events(
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                kind TEXT NOT NULL,
                summary TEXT NOT NULL,
                confidence REAL NOT NULL,
                reversible INTEGER NOT NULL,
                world_fingerprint TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_v5_continuity_run_key ON v5_goal_continuity_runs(run_key)",
            "CREATE INDEX IF NOT EXISTS idx_v5_continuity_events_run ON v5_goal_continuity_events(run_id,revision)",
            "CREATE INDEX IF NOT EXISTS idx_v5_continuity_status ON v5_goal_continuity_runs(status,updated_at)",
        ):
            self.db.execute(sql)

    @staticmethod
    def _row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        out = dict(row)
        out["confidence"] = float(out.get("confidence") or 0.0)
        out["revision"] = int(out.get("revision") or 0)
        out["metadata"] = _load(out.pop("metadata_json", "{}"))
        return out

    def begin(
        self,
        goal: str,
        *,
        run_key: str = "",
        metadata: dict[str, Any] | None = None,
        confidence: float = 0.5,
    ) -> dict[str, Any]:
        goal = " ".join(str(goal or "").split())
        if not goal:
            raise ValueError("goal is required.")
        if len(goal) > 12000:
            raise ValueError("goal is too long.")
        run_key = str(run_key or "").strip()[:240]
        if run_key:
            existing = self.db.execute(
                "SELECT * FROM v5_goal_continuity_runs WHERE run_key=? ORDER BY updated_at DESC",
                (run_key,),
                fetch="one",
            )
            if existing and str(existing.get("status")) not in _TERMINAL_STATUSES:
                return self.get(str(existing["run_id"]))
        now = utc_now()
        run_id = new_id("cont_")
        self.db.execute(
            """INSERT INTO v5_goal_continuity_runs(
                run_id,run_key,goal,status,phase,confidence,revision,world_fingerprint,
                last_observed_at,last_verified_at,created_at,updated_at,metadata_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                run_key or None,
                goal,
                "active",
                "observe",
                _clamp(confidence),
                0,
                None,
                None,
                None,
                now,
                now,
                _json(metadata or {}),
            ),
        )
        self.bus.publish("continuity.started", run_id=run_id, goal=goal)
        return self.get(run_id)

    def get(self, run_id: str, *, event_limit: int = 50) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM v5_goal_continuity_runs WHERE run_id=?", (str(run_id),), fetch="one"
        )
        if not row:
            raise KeyError(f"Unknown continuity run: {run_id}")
        events = self.db.execute(
            """SELECT event_id,run_id,revision,kind,summary,confidence,reversible,
                      world_fingerprint,payload_json,created_at
               FROM v5_goal_continuity_events
               WHERE run_id=? ORDER BY revision DESC LIMIT ?""",
            (str(run_id), max(1, min(int(event_limit), 500))),
            fetch="all",
        ) or []
        for event in events:
            event["confidence"] = float(event.get("confidence") or 0.0)
            event["reversible"] = bool(event.get("reversible"))
            event["payload"] = _load(event.pop("payload_json", "{}"))
        out = self._row(row) or {}
        out["events"] = list(reversed(events))
        return out

    def list(self, *, status: str = "", limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        status = str(status or "").strip().lower()
        if status:
            rows = self.db.execute(
                "SELECT * FROM v5_goal_continuity_runs WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                (status, limit),
                fetch="all",
            ) or []
        else:
            rows = self.db.execute(
                "SELECT * FROM v5_goal_continuity_runs ORDER BY updated_at DESC LIMIT ?",
                (limit,),
                fetch="all",
            ) or []
        return [self._row(row) or {} for row in rows]

    def record(
        self,
        run_id: str,
        kind: str,
        summary: str,
        *,
        payload: dict[str, Any] | None = None,
        confidence: float = 0.7,
        reversible: bool = True,
        world_fingerprint: str = "",
    ) -> dict[str, Any]:
        current = self.get(run_id, event_limit=1)
        if current["status"] in _TERMINAL_STATUSES:
            raise ValueError(f"continuity run is terminal: {current['status']}")
        kind = str(kind or "").strip().lower()
        if kind not in _ALLOWED_EVENT_KINDS:
            raise ValueError(f"kind must be one of: {', '.join(sorted(_ALLOWED_EVENT_KINDS))}")
        if kind == "completion" and not bool((payload or {}).get("verified")):
            raise ValueError("completion requires payload.verified=true.")
        summary = " ".join(str(summary or "").split())
        if not summary:
            raise ValueError("summary is required.")
        summary = summary[:12000]
        confidence = _clamp(confidence)
        revision = int(current["revision"]) + 1
        now = utc_now()
        world_fingerprint = str(world_fingerprint or "").strip()[:240]

        phase = str(current["phase"])
        status = str(current["status"])
        last_observed_at = current.get("last_observed_at")
        last_verified_at = current.get("last_verified_at")
        stored_fingerprint = str(current.get("world_fingerprint") or "")

        if kind == "observe":
            phase = "understand"
            last_observed_at = now
            if world_fingerprint:
                stored_fingerprint = world_fingerprint
        elif kind == "action":
            phase = "verify"
        elif kind == "verification":
            verified = bool((payload or {}).get("verified"))
            last_verified_at = now
            phase = "continue" if verified else "repair"
        elif kind == "failure":
            phase = "repair"
        elif kind == "repair":
            phase = "verify"
        elif kind == "checkpoint":
            phase = "continue"
        elif kind == "blocker":
            phase = "stopped"
            status = "blocked"
        elif kind == "completion":
            phase = "stopped"
            status = "completed"
            last_verified_at = now

        self.db.execute(
            """INSERT INTO v5_goal_continuity_events(
                event_id,run_id,revision,kind,summary,confidence,reversible,
                world_fingerprint,payload_json,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                new_id("cevt_"),
                run_id,
                revision,
                kind,
                summary,
                confidence,
                1 if reversible else 0,
                world_fingerprint or None,
                _json(payload or {}),
                now,
            ),
        )
        self.db.execute(
            """UPDATE v5_goal_continuity_runs
               SET status=?,phase=?,confidence=?,revision=?,world_fingerprint=?,
                   last_observed_at=?,last_verified_at=?,updated_at=? WHERE run_id=?""",
            (
                status,
                phase,
                confidence,
                revision,
                stored_fingerprint or None,
                last_observed_at,
                last_verified_at,
                now,
                run_id,
            ),
        )
        self.bus.publish("continuity.recorded", run_id=run_id, kind=kind, revision=revision)
        return self.get(run_id)

    def assess(
        self,
        run_id: str,
        *,
        world_fingerprint: str = "",
        max_observation_age_seconds: int = 120,
    ) -> dict[str, Any]:
        run = self.get(run_id, event_limit=20)
        max_age = max(1, min(int(max_observation_age_seconds), 86400))
        age = _age_seconds(run.get("last_observed_at"))
        current_fingerprint = str(world_fingerprint or "").strip()[:240]
        previous_fingerprint = str(run.get("world_fingerprint") or "")
        world_changed = bool(current_fingerprint and previous_fingerprint and current_fingerprint != previous_fingerprint)
        observation_stale = age is None or age > max_age
        terminal = run["status"] in _TERMINAL_STATUSES
        latest = run["events"][-1] if run["events"] else None
        latest_kind = str((latest or {}).get("kind") or "")
        latest_verified = bool(((latest or {}).get("payload") or {}).get("verified")) if latest_kind == "verification" else False

        if terminal:
            decision = "stop"
            reason = f"run is {run['status']}"
        elif world_changed or observation_stale:
            decision = "reobserve"
            reason = "desktop/world evidence changed" if world_changed else "observation is missing or stale"
        elif latest_kind in {"action", "repair"}:
            decision = "verify"
            reason = "a state-changing step needs independent verification"
        elif latest_kind == "verification" and not latest_verified:
            decision = "repair"
            reason = "latest verification did not prove the requested end state"
        elif latest_kind == "failure":
            decision = "repair"
            reason = "latest recorded step is a failure"
        else:
            decision = "continue"
            reason = "fresh evidence is available and no blocker is recorded"

        return {
            "mode": "rc12_goal_continuity",
            "run_id": run_id,
            "goal": run["goal"],
            "status": run["status"],
            "phase": run["phase"],
            "revision": run["revision"],
            "decision": decision,
            "reason": reason,
            "confidence": run["confidence"],
            "latest_event_kind": latest_kind or None,
            "observation_age_seconds": round(age, 3) if age is not None else None,
            "max_observation_age_seconds": max_age,
            "observation_stale": observation_stale,
            "world_changed": world_changed,
            "side_effect_replay_allowed": False,
            "permission_bypass_allowed": False,
            "rules": [
                "Re-observe when assumptions may be stale.",
                "Never replay a state-changing action merely because execution resumed.",
                "Verify every meaningful state change before marking progress complete.",
                "Treat blockers and permission boundaries as stop conditions, not retry targets.",
                "Keep continuity inside the user's existing goal and authority scope.",
            ],
        }

    def cancel(self, run_id: str, *, reason: str = "cancelled") -> dict[str, Any]:
        run = self.get(run_id, event_limit=1)
        if run["status"] in _TERMINAL_STATUSES:
            return run
        self.db.execute(
            "UPDATE v5_goal_continuity_runs SET status='cancelled',phase='stopped',updated_at=? WHERE run_id=?",
            (utc_now(), run_id),
        )
        self.bus.publish("continuity.cancelled", run_id=run_id, reason=str(reason or "cancelled")[:1000])
        return self.get(run_id)

    def status(self) -> dict[str, Any]:
        counts = self.db.execute(
            "SELECT status,COUNT(*) AS count FROM v5_goal_continuity_runs GROUP BY status", fetch="all"
        ) or []
        return {
            "mode": "rc12_goal_continuity",
            "persistent": True,
            "side_effect_replay_allowed": False,
            "permission_bypass_allowed": False,
            "fresh_evidence_on_resume": True,
            "verification_after_action": True,
            "event_kinds": sorted(_ALLOWED_EVENT_KINDS),
            "runs_by_status": {str(row["status"]): int(row["count"]) for row in counts},
        }
