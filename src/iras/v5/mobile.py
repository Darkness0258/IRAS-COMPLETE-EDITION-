from __future__ import annotations

import json
from typing import Any

from .common import SQLiteDB, new_id, utc_now


class MobileCompanionHub:
    def __init__(self, db: SQLiteDB):
        self.db = db
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS v5_mobile_devices(
            mobile_id TEXT PRIMARY KEY, name TEXT NOT NULL, platform TEXT NOT NULL,
            created_at TEXT NOT NULL, last_seen TEXT NOT NULL, enabled INTEGER NOT NULL
        )""")
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS v5_mobile_events(
            event_id TEXT PRIMARY KEY, mobile_id TEXT, kind TEXT NOT NULL, payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0
        )""")

    def register(self, name: str, platform: str = "android") -> dict[str, Any]:
        mid = new_id("mob_")
        now = utc_now()
        self.db.execute("INSERT INTO v5_mobile_devices VALUES(?,?,?,?,?,1)", (mid, name[:120], platform[:40], now, now))
        return {"mobile_id": mid, "name": name, "platform": platform}

    def heartbeat(self, mobile_id: str) -> None:
        self.db.execute("UPDATE v5_mobile_devices SET last_seen=? WHERE mobile_id=?", (utc_now(), mobile_id))

    def push_event(self, kind: str, payload: dict[str, Any], mobile_id: str | None = None) -> str:
        eid = new_id("mevt_")
        self.db.execute("INSERT INTO v5_mobile_events VALUES(?,?,?,?,?,0)", (eid, mobile_id, kind, json.dumps(payload, ensure_ascii=False), utc_now()))
        return eid

    def pending(self, mobile_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM v5_mobile_events WHERE delivered=0 AND (mobile_id IS NULL OR mobile_id=?) ORDER BY created_at LIMIT ?",
            (mobile_id, limit), fetch="all"
        ) or []
        for row in rows:
            row["payload"] = json.loads(row.pop("payload_json"))
        return rows

    def acknowledge(self, event_id: str) -> None:
        self.db.execute("UPDATE v5_mobile_events SET delivered=1 WHERE event_id=?", (event_id,))
