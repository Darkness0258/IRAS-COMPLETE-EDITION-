from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable

from .common import SQLiteDB, EventBus, new_id, utc_now, canonical_json


@dataclass
class MonitorResult:
    value: Any
    healthy: bool = True
    summary: str = ""


class ProactiveMonitor:
    """Change/health monitor that notifies only on meaningful transitions."""

    def __init__(self, db: SQLiteDB, bus: EventBus | None = None):
        self.db = db
        self.bus = bus or EventBus()
        self.checkers: dict[str, Callable[[dict[str, Any]], MonitorResult]] = {}
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS v5_monitors(
            monitor_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            config_json TEXT NOT NULL,
            enabled INTEGER NOT NULL,
            last_hash TEXT,
            last_healthy INTEGER,
            last_summary TEXT,
            last_checked TEXT
        )""")

    def register_checker(self, kind: str, checker: Callable[[dict[str, Any]], MonitorResult]) -> None:
        self.checkers[kind] = checker

    def add(self, *, name: str, kind: str, config: dict[str, Any]) -> dict[str, Any]:
        if kind not in self.checkers:
            raise ValueError(f"Unknown monitor kind: {kind}")
        monitor_id = new_id("mon_")
        self.db.execute(
            "INSERT INTO v5_monitors(monitor_id,name,kind,config_json,enabled) VALUES(?,?,?,?,1)",
            (monitor_id, name[:160], kind, json.dumps(config, ensure_ascii=False)),
        )
        return self.get(monitor_id)

    def get(self, monitor_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM v5_monitors WHERE monitor_id=?", (monitor_id,), fetch="one")
        if row:
            row["config"] = json.loads(row.pop("config_json"))
            row["enabled"] = bool(row["enabled"])
        return row

    def list(self) -> list[dict[str, Any]]:
        ids = self.db.execute("SELECT monitor_id FROM v5_monitors ORDER BY name", fetch="all") or []
        return [self.get(r["monitor_id"]) for r in ids]

    def check(self, monitor_id: str) -> dict[str, Any]:
        row = self.get(monitor_id)
        if not row:
            raise KeyError(monitor_id)
        checker = self.checkers.get(row["kind"])
        if not checker:
            raise RuntimeError(f"Checker unavailable: {row['kind']}")
        result = checker(row["config"])
        digest = hashlib.sha256(canonical_json(result.value)).hexdigest()
        changed = row.get("last_hash") not in (None, "") and row.get("last_hash") != digest
        health_changed = row.get("last_healthy") is not None and bool(row.get("last_healthy")) != bool(result.healthy)
        first = not row.get("last_hash")
        self.db.execute(
            "UPDATE v5_monitors SET last_hash=?,last_healthy=?,last_summary=?,last_checked=? WHERE monitor_id=?",
            (digest, int(bool(result.healthy)), result.summary[:4000], utc_now(), monitor_id),
        )
        if changed or health_changed:
            self.bus.publish(
                "monitor.changed", monitor_id=monitor_id, name=row["name"], kind=row["kind"],
                healthy=result.healthy, summary=result.summary, health_changed=health_changed,
            )
        return {"monitor_id": monitor_id, "first": first, "changed": changed, "health_changed": health_changed,
                "healthy": result.healthy, "summary": result.summary, "value": result.value}

    def check_all(self) -> list[dict[str, Any]]:
        out = []
        for row in self.list():
            if row and row["enabled"]:
                try:
                    out.append(self.check(row["monitor_id"]))
                except Exception as exc:
                    out.append({"monitor_id": row["monitor_id"], "healthy": False,
                                "error": f"{type(exc).__name__}: {exc}"})
        return out
