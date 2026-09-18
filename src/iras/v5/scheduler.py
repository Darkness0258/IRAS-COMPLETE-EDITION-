from __future__ import annotations

from datetime import datetime, timezone, timedelta
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any

from .common import SQLiteDB, new_id, utc_now, EventBus


class PersistentScheduler:
    """Restart-safe interval scheduler with pause/resume, leases and bounded concurrency.

    A lease prevents the same due job from being claimed twice by overlapping worker
    loops or multiple application instances sharing PostgreSQL. Jobs are read-only by
    default at the orchestration boundary; this class never grants permissions.
    """

    def __init__(self, db: SQLiteDB, bus: EventBus | None = None):
        self.db = db
        self.bus = bus or EventBus()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._executor: ThreadPoolExecutor | None = None
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS v5_scheduled_jobs(
            job_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            prompt TEXT NOT NULL,
            next_run TEXT NOT NULL,
            interval_seconds INTEGER,
            enabled INTEGER NOT NULL,
            last_run TEXT,
            last_result TEXT,
            failure_count INTEGER NOT NULL DEFAULT 0
        )""")
        for spec in (
            "paused INTEGER NOT NULL DEFAULT 0",
            "run_token TEXT",
            "claim_until TEXT",
            "last_error TEXT",
            "misfire_policy TEXT NOT NULL DEFAULT 'skip'",
        ):
            try:
                self.db.execute(f"ALTER TABLE v5_scheduled_jobs ADD COLUMN {spec}")
            except Exception:
                pass

    @staticmethod
    def _dt(value: str) -> datetime:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    def add(self, *, name: str, prompt: str, next_run: str | None = None,
            interval_seconds: int | None = None, misfire_policy: str = "skip") -> dict[str, Any]:
        if interval_seconds is not None and interval_seconds < 60:
            raise ValueError("Scheduled autonomous intervals must be at least 60 seconds.")
        if misfire_policy not in {"skip", "catch_up_once"}:
            raise ValueError("misfire_policy must be skip or catch_up_once")
        next_run = next_run or utc_now()
        self._dt(next_run)
        job_id = new_id("sched_")
        self.db.execute(
            "INSERT INTO v5_scheduled_jobs(job_id,name,prompt,next_run,interval_seconds,enabled,paused,misfire_policy) VALUES(?,?,?,?,?,1,0,?)",
            (job_id, name[:160], prompt[:12000], next_run, interval_seconds, misfire_policy),
        )
        self.bus.publish("schedule.created", job_id=job_id, name=name)
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM v5_scheduled_jobs WHERE job_id=?", (job_id,), fetch="one")
        if row:
            row["enabled"] = bool(row.get("enabled"))
            row["paused"] = bool(row.get("paused"))
        return row

    def list(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM v5_scheduled_jobs"
        if enabled_only:
            sql += " WHERE enabled=1 AND paused=0"
        sql += " ORDER BY next_run"
        rows = self.db.execute(sql, fetch="all") or []
        for row in rows:
            row["enabled"] = bool(row.get("enabled")); row["paused"] = bool(row.get("paused"))
        return rows

    def pause(self, job_id: str) -> dict[str, Any]:
        self.db.execute("UPDATE v5_scheduled_jobs SET paused=1 WHERE job_id=?", (job_id,))
        self.bus.publish("schedule.paused", job_id=job_id)
        return self.get(job_id) or {}

    def resume(self, job_id: str, *, next_run: str | None = None) -> dict[str, Any]:
        if next_run:
            self._dt(next_run)
            self.db.execute("UPDATE v5_scheduled_jobs SET paused=0,enabled=1,next_run=? WHERE job_id=?", (next_run, job_id))
        else:
            self.db.execute("UPDATE v5_scheduled_jobs SET paused=0,enabled=1 WHERE job_id=?", (job_id,))
        self.bus.publish("schedule.resumed", job_id=job_id)
        return self.get(job_id) or {}

    def cancel(self, job_id: str) -> None:
        self.db.execute("UPDATE v5_scheduled_jobs SET enabled=0,run_token=NULL,claim_until=NULL WHERE job_id=?", (job_id,))
        self.bus.publish("schedule.cancelled", job_id=job_id)

    def delete(self, job_id: str) -> None:
        self.db.execute("DELETE FROM v5_scheduled_jobs WHERE job_id=?", (job_id,))
        self.bus.publish("schedule.deleted", job_id=job_id)

    def _release_expired_claims(self) -> None:
        now = utc_now()
        self.db.execute(
            "UPDATE v5_scheduled_jobs SET run_token=NULL,claim_until=NULL WHERE claim_until IS NOT NULL AND claim_until<?",
            (now,),
        )

    def _claim_due(self, *, lease_seconds: int = 900, limit: int = 32) -> list[dict[str, Any]]:
        self._release_expired_claims()
        now = utc_now()
        rows = self.db.execute(
            "SELECT job_id FROM v5_scheduled_jobs WHERE enabled=1 AND paused=0 AND next_run<=? AND run_token IS NULL ORDER BY next_run LIMIT ?",
            (now, max(1, int(limit))), fetch="all"
        ) or []
        claimed: list[dict[str, Any]] = []
        until = (datetime.now(timezone.utc) + timedelta(seconds=max(60, lease_seconds))).isoformat()
        for item in rows:
            token = new_id("lease_")
            self.db.execute(
                "UPDATE v5_scheduled_jobs SET run_token=?,claim_until=? WHERE job_id=? AND run_token IS NULL",
                (token, until, item["job_id"]),
            )
            row = self.get(item["job_id"])
            if row and row.get("run_token") == token:
                row["_lease_token"] = token
                claimed.append(row)
        return claimed

    def finish(self, job_id: str, *, result: str, ok: bool = True, lease_token: str | None = None) -> None:
        row = self.get(job_id)
        if not row:
            raise KeyError(job_id)
        if lease_token and row.get("run_token") not in {lease_token, None, ""}:
            raise RuntimeError("Scheduled job lease is no longer owned by this worker.")
        now = datetime.now(timezone.utc)
        interval = row.get("interval_seconds")
        if interval:
            previous = self._dt(str(row["next_run"]))
            if row.get("misfire_policy") == "catch_up_once" and previous + timedelta(seconds=int(interval)) > now:
                next_dt = previous + timedelta(seconds=int(interval))
            else:
                next_dt = now + timedelta(seconds=int(interval))
            next_run = next_dt.isoformat(); enabled = 1
        else:
            next_run = row["next_run"]; enabled = 0
        failures = 0 if ok else int(row.get("failure_count") or 0) + 1
        last_error = "" if ok else result[:4000]
        self.db.execute(
            "UPDATE v5_scheduled_jobs SET next_run=?,enabled=?,last_run=?,last_result=?,failure_count=?,last_error=?,run_token=NULL,claim_until=NULL WHERE job_id=?",
            (next_run, enabled, now.isoformat(), result[:16000], failures, last_error, job_id),
        )
        self.bus.publish("schedule.finished", job_id=job_id, ok=ok, next_run=next_run)

    def _execute_claim(self, row: dict[str, Any], executor: Callable[[str, dict[str, Any]], Any]) -> dict[str, Any]:
        token = row.get("_lease_token")
        try:
            out = executor(row["prompt"], row)
            text = str(out)
            self.finish(row["job_id"], result=text, ok=True, lease_token=token)
            return {"job_id": row["job_id"], "ok": True, "result": text}
        except Exception as exc:
            text = f"{type(exc).__name__}: {exc}"
            try:
                self.finish(row["job_id"], result=text, ok=False, lease_token=token)
            except Exception:
                pass
            return {"job_id": row["job_id"], "ok": False, "error": text}

    def run_due(self, executor: Callable[[str, dict[str, Any]], Any], *, max_claims: int = 32) -> list[dict[str, Any]]:
        return [self._execute_claim(row, executor) for row in self._claim_due(limit=max_claims)]

    def start(self, executor: Callable[[str, dict[str, Any]], Any], *, poll_seconds: float = 5.0, max_workers: int = 4) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._executor = ThreadPoolExecutor(max_workers=max(1, min(int(max_workers), 16)), thread_name_prefix="iras-v5-scheduled")
        def loop():
            while not self._stop.is_set():
                for row in self._claim_due(limit=max_workers):
                    if self._executor:
                        self._executor.submit(self._execute_claim, row, executor)
                self._stop.wait(max(1.0, poll_seconds))
        self._thread = threading.Thread(target=loop, name="iras-v5-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=False)
        self._executor = None
