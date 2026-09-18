from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import hashlib
import json
import threading
from typing import Any, Callable

from .common import SQLiteDB, EventBus, new_id, utc_now, canonical_json


@dataclass
class MonitorResult:
    value: Any
    healthy: bool = True
    summary: str = ""


class ProactiveMonitor:
    """Durable proactive monitor with interval scheduling and transition-only events."""

    def __init__(self, db: SQLiteDB, bus: EventBus | None = None):
        self.db = db; self.bus = bus or EventBus(); self.checkers: dict[str, Callable[[dict[str, Any]], MonitorResult]] = {}
        self._stop = threading.Event(); self._thread: threading.Thread | None = None
        self.db.execute("""CREATE TABLE IF NOT EXISTS v5_monitors(
            monitor_id TEXT PRIMARY KEY,name TEXT NOT NULL,kind TEXT NOT NULL,config_json TEXT NOT NULL,
            enabled INTEGER NOT NULL,last_hash TEXT,last_healthy INTEGER,last_summary TEXT,last_checked TEXT)""")
        for spec in (
            "interval_seconds INTEGER NOT NULL DEFAULT 300",
            "next_check TEXT",
            "last_error TEXT",
            "failure_count INTEGER NOT NULL DEFAULT 0",
        ):
            try: self.db.execute(f"ALTER TABLE v5_monitors ADD COLUMN {spec}")
            except Exception: pass

    def register_checker(self, kind: str, checker: Callable[[dict[str, Any]], MonitorResult]) -> None:
        self.checkers[kind] = checker

    def add(self, *, name: str, kind: str, config: dict[str, Any], interval_seconds: int = 300) -> dict[str, Any]:
        if kind not in self.checkers: raise ValueError(f"Unknown monitor kind: {kind}")
        interval_seconds=max(60,min(int(interval_seconds),86400))
        monitor_id = new_id("mon_"); next_check=utc_now()
        self.db.execute(
            "INSERT INTO v5_monitors(monitor_id,name,kind,config_json,enabled,interval_seconds,next_check) VALUES(?,?,?,?,1,?,?)",
            (monitor_id, name[:160], kind, json.dumps(config, ensure_ascii=False), interval_seconds, next_check),
        )
        return self.get(monitor_id)

    def get(self, monitor_id: str) -> dict[str, Any] | None:
        row=self.db.execute("SELECT * FROM v5_monitors WHERE monitor_id=?",(monitor_id,),fetch="one")
        if row:
            row["config"]=json.loads(row.pop("config_json")); row["enabled"]=bool(row["enabled"])
        return row

    def list(self) -> list[dict[str, Any]]:
        ids=self.db.execute("SELECT monitor_id FROM v5_monitors ORDER BY name",fetch="all") or []
        return [self.get(r["monitor_id"]) for r in ids]

    def pause(self, monitor_id: str) -> dict[str, Any]:
        self.db.execute("UPDATE v5_monitors SET enabled=0 WHERE monitor_id=?",(monitor_id,)); return self.get(monitor_id) or {}

    def resume(self, monitor_id: str) -> dict[str, Any]:
        self.db.execute("UPDATE v5_monitors SET enabled=1,next_check=? WHERE monitor_id=?",(utc_now(),monitor_id)); return self.get(monitor_id) or {}

    def delete(self, monitor_id: str) -> None:
        self.db.execute("DELETE FROM v5_monitors WHERE monitor_id=?",(monitor_id,))

    def check(self, monitor_id: str) -> dict[str, Any]:
        row=self.get(monitor_id)
        if not row: raise KeyError(monitor_id)
        checker=self.checkers.get(row["kind"])
        if not checker: raise RuntimeError(f"Checker unavailable: {row['kind']}")
        try:
            result=checker(row["config"])
            digest=hashlib.sha256(canonical_json(result.value)).hexdigest()
            changed=row.get("last_hash") not in (None,"") and row.get("last_hash")!=digest
            health_changed=row.get("last_healthy") is not None and bool(row.get("last_healthy"))!=bool(result.healthy)
            first=not row.get("last_hash")
            next_check=(datetime.now(timezone.utc)+timedelta(seconds=int(row.get("interval_seconds") or 300))).isoformat()
            self.db.execute("UPDATE v5_monitors SET last_hash=?,last_healthy=?,last_summary=?,last_checked=?,next_check=?,last_error='',failure_count=0 WHERE monitor_id=?",
                            (digest,int(bool(result.healthy)),result.summary[:4000],utc_now(),next_check,monitor_id))
            if changed or health_changed:
                self.bus.publish("monitor.changed",monitor_id=monitor_id,name=row["name"],kind=row["kind"],healthy=result.healthy,summary=result.summary,health_changed=health_changed)
            return {"monitor_id":monitor_id,"first":first,"changed":changed,"health_changed":health_changed,"healthy":result.healthy,"summary":result.summary,"value":result.value}
        except Exception as exc:
            failures=int(row.get("failure_count") or 0)+1
            next_check=(datetime.now(timezone.utc)+timedelta(seconds=min(3600,max(60,int(row.get("interval_seconds") or 300)*min(failures,6))))).isoformat()
            err=f"{type(exc).__name__}: {exc}"
            self.db.execute("UPDATE v5_monitors SET last_checked=?,next_check=?,last_error=?,failure_count=? WHERE monitor_id=?",(utc_now(),next_check,err[:4000],failures,monitor_id))
            self.bus.publish("monitor.error",monitor_id=monitor_id,name=row["name"],error=err)
            raise

    def due(self) -> list[dict[str, Any]]:
        now=utc_now()
        rows=self.db.execute("SELECT monitor_id FROM v5_monitors WHERE enabled=1 AND (next_check IS NULL OR next_check<=?) ORDER BY next_check",(now,),fetch="all") or []
        return [self.get(r["monitor_id"]) for r in rows]

    def check_due(self) -> list[dict[str, Any]]:
        out=[]
        for row in self.due():
            if not row: continue
            try: out.append(self.check(row["monitor_id"]))
            except Exception as exc: out.append({"monitor_id":row["monitor_id"],"healthy":False,"error":f"{type(exc).__name__}: {exc}"})
        return out

    def check_all(self) -> list[dict[str, Any]]:
        out=[]
        for row in self.list():
            if row and row["enabled"]:
                try: out.append(self.check(row["monitor_id"]))
                except Exception as exc: out.append({"monitor_id":row["monitor_id"],"healthy":False,"error":f"{type(exc).__name__}: {exc}"})
        return out

    def start(self, *, poll_seconds: float = 15.0) -> None:
        if self._thread and self._thread.is_alive(): return
        self._stop.clear()
        def loop():
            while not self._stop.is_set():
                self.check_due(); self._stop.wait(max(2.0,poll_seconds))
        self._thread=threading.Thread(target=loop,name="iras-v5-monitor",daemon=True); self._thread.start()

    def stop(self) -> None:
        self._stop.set()
