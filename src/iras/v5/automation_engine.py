from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .common import EventBus, SQLiteDB, new_id, utc_now


PERMISSION_MODES = ("read_only", "safe_action", "system_action", "critical")
TRIGGER_TYPES = ("manual", "interval", "once", "event")
ACTION_KINDS = ("prompt", "workflow")


class AutomationEngine:
    """Persistent IRAS automation engine with fail-closed authority boundaries.

    Trigger persistence and execution state live here. Authority does not: interactive
    executions re-enter ToolRegistry permission checks, while unattended state-changing
    runs require a local authorizer (normally autonomous Master Control on the owner's PC).
    """

    def __init__(self, db: SQLiteDB, bus: EventBus | None = None):
        self.db = db
        self.bus = bus or EventBus()
        self._executor_fn: Callable[[dict[str, Any], dict[str, Any]], Any] | None = None
        self._unattended_authorizer: Callable[[dict[str, Any]], bool] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pool: ThreadPoolExecutor | None = None
        self._unsubscribe = self.bus.subscribe("*", self._on_bus_event)
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS v5_automations(
                automation_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                action_kind TEXT NOT NULL,
                prompt TEXT NOT NULL,
                action_ref TEXT,
                permission_mode TEXT NOT NULL,
                trigger_type TEXT NOT NULL,
                trigger_json TEXT NOT NULL,
                next_run TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                paused INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ready',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_run TEXT,
                last_result TEXT,
                last_error TEXT,
                last_trigger TEXT,
                failure_count INTEGER NOT NULL DEFAULT 0,
                run_token TEXT,
                claim_until TEXT
            )
            """
        )

    @staticmethod
    def _dt(value: str) -> datetime:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    @staticmethod
    def _loads(value: str | None) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _dumps(value: dict[str, Any]) -> str:
        return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def bind_executor(
        self,
        executor: Callable[[dict[str, Any], dict[str, Any]], Any],
        *,
        unattended_authorizer: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        self._executor_fn = executor
        if unattended_authorizer is not None:
            self._unattended_authorizer = unattended_authorizer

    def bind_unattended_authorizer(self, checker: Callable[[dict[str, Any]], bool] | None) -> None:
        self._unattended_authorizer = checker

    def add(
        self,
        *,
        name: str,
        action_kind: str = "prompt",
        prompt: str = "",
        action_ref: str = "",
        permission_mode: str = "read_only",
        trigger_type: str = "manual",
        trigger: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action_kind = str(action_kind or "prompt").strip().lower()
        permission_mode = str(permission_mode or "read_only").strip().lower()
        trigger_type = str(trigger_type or "manual").strip().lower()
        trigger = dict(trigger or {})
        if action_kind not in ACTION_KINDS:
            raise ValueError(f"action_kind must be one of {ACTION_KINDS}")
        if permission_mode not in PERMISSION_MODES:
            raise ValueError(f"permission_mode must be one of {PERMISSION_MODES}")
        if trigger_type not in TRIGGER_TYPES:
            raise ValueError(f"trigger_type must be one of {TRIGGER_TYPES}")
        if action_kind == "prompt" and not str(prompt).strip():
            raise ValueError("Prompt automations require a non-empty prompt.")
        if action_kind == "workflow" and not str(action_ref).strip():
            raise ValueError("Workflow automations require an action_ref workflow id.")

        next_run: str | None = None
        if trigger_type == "interval":
            seconds = int(trigger.get("seconds") or 0)
            if seconds < 60 or seconds > 31536000:
                raise ValueError("Interval automation seconds must be between 60 and 31536000.")
            start_at = str(trigger.get("start_at") or "").strip()
            next_run = self._dt(start_at).isoformat() if start_at else (
                datetime.now(timezone.utc) + timedelta(seconds=seconds)
            ).isoformat()
            trigger["seconds"] = seconds
        elif trigger_type == "once":
            at = str(trigger.get("at") or "").strip()
            if not at:
                raise ValueError("Once automations require trigger.at as an ISO timestamp.")
            next_run = self._dt(at).isoformat()
            trigger["at"] = next_run
        elif trigger_type == "event":
            event = str(trigger.get("event") or "").strip()
            if not event or len(event) > 200:
                raise ValueError("Event automations require trigger.event.")
            trigger["event"] = event
            match = trigger.get("match") or {}
            if not isinstance(match, dict):
                raise ValueError("trigger.match must be an object.")
            trigger["match"] = match

        automation_id = new_id("auto_")
        now = utc_now()
        self.db.execute(
            """INSERT INTO v5_automations(
                automation_id,name,action_kind,prompt,action_ref,permission_mode,
                trigger_type,trigger_json,next_run,enabled,paused,status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,1,0,'ready',?,?)""",
            (
                automation_id,
                str(name or "Automation")[:160],
                action_kind,
                str(prompt or "")[:12000],
                str(action_ref or "")[:160],
                permission_mode,
                trigger_type,
                self._dumps(trigger),
                next_run,
                now,
                now,
            ),
        )
        self.bus.publish(
            "automation.created",
            automation_id=automation_id,
            name=str(name or "Automation")[:160],
            trigger_type=trigger_type,
            permission_mode=permission_mode,
        )
        return self.get(automation_id) or {}

    def get(self, automation_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM v5_automations WHERE automation_id=?",
            (automation_id,),
            fetch="one",
        )
        if not row:
            return None
        row["enabled"] = bool(row.get("enabled"))
        row["paused"] = bool(row.get("paused"))
        row["trigger"] = self._loads(row.get("trigger_json"))
        row.pop("trigger_json", None)
        return row

    def list(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT automation_id FROM v5_automations"
        if enabled_only:
            sql += " WHERE enabled=1 AND paused=0"
        sql += " ORDER BY created_at DESC"
        ids = self.db.execute(sql, fetch="all") or []
        rows: list[dict[str, Any]] = []
        for item in ids:
            row = self.get(str(item["automation_id"]))
            if row:
                rows.append(row)
        return rows

    def pause(self, automation_id: str) -> dict[str, Any]:
        self.db.execute(
            "UPDATE v5_automations SET paused=1,status='paused',updated_at=? WHERE automation_id=?",
            (utc_now(), automation_id),
        )
        self.bus.publish("automation.paused", automation_id=automation_id)
        return self.get(automation_id) or {}

    def resume(self, automation_id: str) -> dict[str, Any]:
        row = self.get(automation_id)
        if not row:
            raise KeyError(automation_id)
        next_run = row.get("next_run")
        trigger = row.get("trigger") or {}
        if row.get("trigger_type") == "interval" and not next_run:
            next_run = (
                datetime.now(timezone.utc) + timedelta(seconds=int(trigger.get("seconds") or 60))
            ).isoformat()
        self.db.execute(
            "UPDATE v5_automations SET paused=0,enabled=1,status='ready',next_run=?,updated_at=? WHERE automation_id=?",
            (next_run, utc_now(), automation_id),
        )
        self.bus.publish("automation.resumed", automation_id=automation_id)
        return self.get(automation_id) or {}

    def cancel(self, automation_id: str) -> dict[str, Any]:
        self.db.execute(
            """UPDATE v5_automations
               SET enabled=0,paused=0,status='cancelled',run_token=NULL,claim_until=NULL,updated_at=?
               WHERE automation_id=?""",
            (utc_now(), automation_id),
        )
        self.bus.publish("automation.cancelled", automation_id=automation_id)
        return self.get(automation_id) or {}

    def delete(self, automation_id: str) -> None:
        self.db.execute("DELETE FROM v5_automations WHERE automation_id=?", (automation_id,))
        self.bus.publish("automation.deleted", automation_id=automation_id)

    def required_permission(self, automation_id: str) -> str:
        row = self.get(automation_id)
        if not row:
            raise KeyError(automation_id)
        return str(row.get("permission_mode") or "read_only")

    @staticmethod
    def _matches(expected: dict[str, Any], payload: dict[str, Any]) -> bool:
        return all(payload.get(key) == value for key, value in expected.items())

    def _on_bus_event(self, event) -> None:
        topic = str(getattr(event, "topic", "") or "")
        if not topic or topic.startswith("automation."):
            return
        payload = dict(getattr(event, "payload", {}) or {})
        self.emit_event(topic, payload, interactive=False)

    def emit_event(
        self,
        event: str,
        payload: dict[str, Any] | None = None,
        *,
        interactive: bool = False,
    ) -> list[dict[str, Any]]:
        event = str(event or "").strip()
        payload = dict(payload or {})
        if not event:
            raise ValueError("event is required")
        results: list[dict[str, Any]] = []
        for row in self.list(enabled_only=True):
            if row.get("trigger_type") != "event":
                continue
            trigger = row.get("trigger") or {}
            if str(trigger.get("event") or "") != event:
                continue
            if not self._matches(dict(trigger.get("match") or {}), payload):
                continue
            results.append(
                self._execute(
                    row,
                    source=f"event:{event}",
                    payload={"event": event, **payload},
                    interactive=interactive,
                )
            )
        return results

    def run_now(
        self,
        automation_id: str,
        *,
        payload: dict[str, Any] | None = None,
        interactive: bool = True,
    ) -> dict[str, Any]:
        row = self.get(automation_id)
        if not row:
            raise KeyError(automation_id)
        if not row.get("enabled"):
            raise RuntimeError("Automation is cancelled or disabled.")
        if row.get("paused"):
            raise RuntimeError("Automation is paused.")
        return self._execute(row, source="manual", payload=dict(payload or {}), interactive=interactive)

    def _release_expired_claims(self) -> None:
        self.db.execute(
            """UPDATE v5_automations SET run_token=NULL,claim_until=NULL
               WHERE claim_until IS NOT NULL AND claim_until<?""",
            (utc_now(),),
        )

    def _claim_due(self, *, limit: int = 16, lease_seconds: int = 900) -> list[dict[str, Any]]:
        self._release_expired_claims()
        ids = self.db.execute(
            """SELECT automation_id FROM v5_automations
               WHERE enabled=1 AND paused=0 AND trigger_type IN ('interval','once')
                 AND next_run IS NOT NULL AND next_run<=? AND run_token IS NULL
               ORDER BY next_run LIMIT ?""",
            (utc_now(), max(1, int(limit))),
            fetch="all",
        ) or []
        until = (
            datetime.now(timezone.utc) + timedelta(seconds=max(60, int(lease_seconds)))
        ).isoformat()
        claimed: list[dict[str, Any]] = []
        for item in ids:
            token = new_id("lease_")
            automation_id = str(item["automation_id"])
            self.db.execute(
                """UPDATE v5_automations SET run_token=?,claim_until=?
                   WHERE automation_id=? AND run_token IS NULL""",
                (token, until, automation_id),
            )
            row = self.get(automation_id)
            raw = self.db.execute(
                "SELECT run_token FROM v5_automations WHERE automation_id=?",
                (automation_id,),
                fetch="one",
            ) or {}
            if row and raw.get("run_token") == token:
                row["_lease_token"] = token
                claimed.append(row)
        return claimed

    def _advance_schedule(
        self,
        row: dict[str, Any],
        *,
        waiting_authorization: bool = False,
    ) -> tuple[str | None, int, int]:
        trigger_type = str(row.get("trigger_type") or "")
        trigger = row.get("trigger") or {}
        if trigger_type == "interval":
            seconds = int(trigger.get("seconds") or 60)
            return (
                (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(),
                1,
                0,
            )
        if trigger_type == "once" and waiting_authorization:
            return (row.get("next_run"), 1, 1)
        if trigger_type == "once":
            return (row.get("next_run"), 0, 0)
        return (
            row.get("next_run"),
            int(bool(row.get("enabled"))),
            int(bool(row.get("paused"))),
        )

    def _store_result(
        self,
        row: dict[str, Any],
        *,
        ok: bool,
        result: str,
        status: str,
        source: str,
        waiting_authorization: bool = False,
    ) -> None:
        next_run, enabled, paused = self._advance_schedule(
            row,
            waiting_authorization=waiting_authorization,
        )
        failures = 0 if ok else int(row.get("failure_count") or 0) + 1
        self.db.execute(
            """UPDATE v5_automations
               SET next_run=?,enabled=?,paused=?,status=?,last_run=?,last_result=?,
                   last_error=?,last_trigger=?,failure_count=?,run_token=NULL,claim_until=NULL,updated_at=?
               WHERE automation_id=?""",
            (
                next_run,
                enabled,
                paused,
                status,
                utc_now(),
                result[:16000],
                "" if ok else result[:4000],
                source[:240],
                failures,
                utc_now(),
                row["automation_id"],
            ),
        )

    def _execute(
        self,
        row: dict[str, Any],
        *,
        source: str,
        payload: dict[str, Any],
        interactive: bool,
    ) -> dict[str, Any]:
        automation_id = str(row["automation_id"])
        permission = str(row.get("permission_mode") or "read_only")
        if not interactive and permission != "read_only":
            allowed = bool(
                self._unattended_authorizer
                and self._unattended_authorizer(dict(row))
            )
            if not allowed:
                message = (
                    "Waiting for owner authorization: unattended state-changing automation "
                    "requires locally armed autonomous Master Control."
                )
                self._store_result(
                    row,
                    ok=False,
                    result=message,
                    status="waiting_authorization",
                    source=source,
                    waiting_authorization=True,
                )
                self.bus.publish(
                    "automation.authorization_required",
                    automation_id=automation_id,
                    permission_mode=permission,
                    source=source,
                )
                return {
                    "automation_id": automation_id,
                    "ok": False,
                    "status": "waiting_authorization",
                    "error": message,
                }

        if self._executor_fn is None:
            raise RuntimeError("Automation executor is not bound.")
        self.db.execute(
            "UPDATE v5_automations SET status='running',updated_at=? WHERE automation_id=?",
            (utc_now(), automation_id),
        )
        self.bus.publish(
            "automation.started",
            automation_id=automation_id,
            source=source,
            permission_mode=permission,
        )
        try:
            output = self._executor_fn(dict(row), dict(payload))
            text = str(output)
            self._store_result(row, ok=True, result=text, status="succeeded", source=source)
            self.bus.publish(
                "automation.finished",
                automation_id=automation_id,
                ok=True,
                source=source,
            )
            return {
                "automation_id": automation_id,
                "ok": True,
                "status": "succeeded",
                "result": output,
            }
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self._store_result(row, ok=False, result=message, status="failed", source=source)
            self.bus.publish(
                "automation.finished",
                automation_id=automation_id,
                ok=False,
                source=source,
                error=message[:1000],
            )
            return {
                "automation_id": automation_id,
                "ok": False,
                "status": "failed",
                "error": message,
            }

    def run_due(self, *, max_claims: int = 16) -> list[dict[str, Any]]:
        return [
            self._execute(
                row,
                source=str(row.get("trigger_type") or "timer"),
                payload={},
                interactive=False,
            )
            for row in self._claim_due(limit=max_claims)
        ]

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, *, poll_seconds: float = 2.0, max_workers: int = 4) -> None:
        if self.running:
            return
        self._stop.clear()
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, min(int(max_workers), 16)),
            thread_name_prefix="iras-v5-automation",
        )

        def loop() -> None:
            while not self._stop.is_set():
                for row in self._claim_due(limit=max_workers):
                    if self._pool:
                        self._pool.submit(
                            self._execute,
                            row,
                            source=str(row.get("trigger_type") or "timer"),
                            payload={},
                            interactive=False,
                        )
                self._stop.wait(max(0.5, float(poll_seconds)))

        self._thread = threading.Thread(
            target=loop,
            name="iras-v5-automation",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=False)
        self._pool = None
