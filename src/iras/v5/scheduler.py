from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
import threading
import time
from typing import Callable, Any

from .common import SQLiteDB, new_id, utc_now, EventBus


@dataclass
class ScheduledJob:
    job_id: str
    name: str
    prompt: str
    next_run: str
    interval_seconds: int | None = None
    enabled: bool = True
    last_run: str | None = None
    last_result: str | None = None
    failure_count: int = 0


class PersistentScheduler:
    """Durable interval scheduler for autonomous IRAS jobs.

    Execution is injected by the caller. This keeps scheduling separate from
    permissions: a scheduled job receives only the executor/capabilities the
    parent runtime explicitly grants it.
    """

    def __init__(self, db: SQLiteDB, bus: EventBus | None = None):
        self.db = db
        self.bus = bus or EventBus()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
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

    @staticmethod
    def _dt(value: str) -> datetime:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    def add(self, *, name: str, prompt: str, next_run: str | None = None, interval_seconds: int | None = None) -> dict[str, Any]:
        if interval_seconds is not None and interval_seconds < 60:
            raise ValueError("Scheduled autonomous intervals must be at least 60 seconds.")
        next_run = next_run or utc_now()
        self._dt(next_run)
        job_id = new_id("sched_")
        self.db.execute(
            "INSERT INTO v5_scheduled_jobs(job_id,name,prompt,next_run,interval_seconds,enabled) VALUES(?,?,?,?,?,1)",
            (job_id, name[:160], prompt[:12000], next_run, interval_seconds),
        )
        self.bus.publish("schedule.created", job_id=job_id, name=name)
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM v5_scheduled_jobs WHERE job_id=?", (job_id,), fetch="one")
        if row:
            row["enabled"] = bool(row["enabled"])
        return row

    def list(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM v5_scheduled_jobs"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY next_run"
        rows = self.db.execute(sql, fetch="all") or []
        for row in rows:
            row["enabled"] = bool(row["enabled"])
        return rows

    def due(self, now: str | None = None) -> list[dict[str, Any]]:
        now = now or utc_now()
        return self.db.execute(
            "SELECT * FROM v5_scheduled_jobs WHERE enabled=1 AND next_run<=? ORDER BY next_run",
            (now,), fetch="all"
        ) or []

    def finish(self, job_id: str, *, result: str, ok: bool = True) -> None:
        row = self.get(job_id)
        if not row:
            raise KeyError(job_id)
        now = datetime.now(timezone.utc)
        interval = row.get("interval_seconds")
        if interval:
            next_run = (now + timedelta(seconds=int(interval))).isoformat()
            enabled = 1
        else:
            next_run = row["next_run"]
            enabled = 0
        failures = 0 if ok else int(row.get("failure_count") or 0) + 1
        self.db.execute(
            "UPDATE v5_scheduled_jobs SET next_run=?,enabled=?,last_run=?,last_result=?,failure_count=? WHERE job_id=?",
            (next_run, enabled, now.isoformat(), result[:16000], failures, job_id),
        )
        self.bus.publish("schedule.finished", job_id=job_id, ok=ok, next_run=next_run)

    def cancel(self, job_id: str) -> None:
        self.db.execute("UPDATE v5_scheduled_jobs SET enabled=0 WHERE job_id=?", (job_id,))
        self.bus.publish("schedule.cancelled", job_id=job_id)

    def run_due(self, executor: Callable[[str, dict[str, Any]], Any]) -> list[dict[str, Any]]:
        results = []
        for row in self.due():
            try:
                out = executor(row["prompt"], row)
                text = str(out)
                self.finish(row["job_id"], result=text, ok=True)
                results.append({"job_id": row["job_id"], "ok": True, "result": text})
            except Exception as exc:
                text = f"{type(exc).__name__}: {exc}"
                self.finish(row["job_id"], result=text, ok=False)
                results.append({"job_id": row["job_id"], "ok": False, "error": text})
        return results

    def start(self, executor: Callable[[str, dict[str, Any]], Any], *, poll_seconds: float = 5.0) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        def loop():
            while not self._stop.is_set():
                self.run_due(executor)
                self._stop.wait(max(1.0, poll_seconds))
        self._thread = threading.Thread(target=loop, name="iras-v5-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
