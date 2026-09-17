from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable

from .common import SQLiteDB, EventBus, new_id, utc_now


@dataclass
class Notification:
    notification_id: str
    title: str
    body: str
    severity: str
    channel: str
    created_at: str
    read: bool = False


class NotificationCenter:
    def __init__(self, db: SQLiteDB, bus: EventBus | None = None):
        self.db = db
        self.bus = bus or EventBus()
        self.channels: dict[str, Callable[[Notification], Any]] = {}
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS v5_notifications(
            notification_id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,
            severity TEXT NOT NULL,channel TEXT NOT NULL,created_at TEXT NOT NULL,read INTEGER NOT NULL
        )""")

    def register_channel(self, name: str, sender: Callable[[Notification], Any]) -> None:
        self.channels[name] = sender

    def notify(self, title: str, body: str, *, severity: str = "info", channel: str = "browser") -> Notification:
        n = Notification(new_id("note_"), title[:240], body[:8000], severity, channel, utc_now())
        self.db.execute("INSERT INTO v5_notifications VALUES(?,?,?,?,?,?,0)",
                        (n.notification_id,n.title,n.body,n.severity,n.channel,n.created_at))
        sender = self.channels.get(channel)
        if sender:
            try: sender(n)
            except Exception: pass
        self.bus.publish("notification.created", notification_id=n.notification_id, title=n.title, severity=severity, channel=channel)
        return n

    def list(self, *, unread_only: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM v5_notifications"
        params: list[Any] = []
        if unread_only: sql += " WHERE read=0"
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        rows = self.db.execute(sql, tuple(params), fetch="all") or []
        for row in rows: row["read"] = bool(row["read"])
        return rows

    def mark_read(self, notification_id: str) -> None:
        self.db.execute("UPDATE v5_notifications SET read=1 WHERE notification_id=?", (notification_id,))
