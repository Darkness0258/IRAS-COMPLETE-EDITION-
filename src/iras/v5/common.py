from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
import uuid
from typing import Any, Callable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str = "") -> str:
    value = uuid.uuid4().hex
    return f"{prefix}{value}" if prefix else value


class SQLiteDB:
    """Thread-safe SQL state backend.

    Uses PostgreSQL when DATABASE_URL is supplied (for restart-safe cloud
    autonomy) and SQLite otherwise (desktop/local development).
    """

    def __init__(self, path: str | Path, database_url: str = ""):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.database_url = str(database_url or "").strip()
        self._postgres = bool(self.database_url)
        self._lock = threading.RLock()
        self._connection = None
        self._psycopg = None
        self._dict_row = None
        if self._postgres:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError("PostgreSQL v5 state requires psycopg; install iras-agent[cloud].") from exc
            self._psycopg = psycopg
            self._dict_row = dict_row

    def connect(self):
        if self._postgres:
            if self._connection is None or self._connection.closed:
                self._connection = self._psycopg.connect(
                    self.database_url, row_factory=self._dict_row, autocommit=True, connect_timeout=10
                )
            return self._connection
        conn = sqlite3.connect(self.path, timeout=20, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self._postgres else sql

    def execute(self, sql: str, params=(), *, fetch: str | None = None):
        with self._lock:
            conn = self.connect()
            cur = conn.cursor()
            try:
                cur.execute(self._sql(sql), params)
                if fetch == "one":
                    row = cur.fetchone()
                    return dict(row) if row else None
                if fetch == "all":
                    return [dict(r) for r in cur.fetchall()]
                if not self._postgres:
                    conn.commit()
                return getattr(cur, "lastrowid", None)
            finally:
                cur.close()
                if not self._postgres:
                    conn.close()


@dataclass
class Event:
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: new_id("evt_"))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventBus:
    def __init__(self):
        self._subs: dict[str, list[Callable[[Event], None]]] = {}
        self._lock = threading.RLock()
        self._history: list[Event] = []

    def subscribe(self, topic: str, callback: Callable[[Event], None]) -> Callable[[], None]:
        with self._lock:
            self._subs.setdefault(topic, []).append(callback)
        def unsubscribe():
            with self._lock:
                if callback in self._subs.get(topic, []):
                    self._subs[topic].remove(callback)
        return unsubscribe

    def publish(self, topic: str, **payload: Any) -> Event:
        event = Event(topic=topic, payload=payload)
        with self._lock:
            self._history.append(event)
            callbacks = list(self._subs.get(topic, [])) + list(self._subs.get("*", []))
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                continue
        return event

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return [e.as_dict() for e in self._history[-max(1, limit):]]


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
