from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from iras.v5.common import SQLiteDB, new_id, utc_now


@dataclass(slots=True)
class CloudThread:
    thread_id: str
    title: str
    created_at: str
    updated_at: str
    archived: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "archived": self.archived,
        }


class CloudStateStore:
    """Restart-safe single-account cloud workspace shared by all IRAS clients.

    Authentication remains at the FastAPI layer. This store deliberately does
    not hold API/device secrets; it only persists client presence, cloud chat
    threads/messages and non-secret UI preferences. It uses the same portable
    SQLite/PostgreSQL backend as the rest of the v5 state layer.
    """

    def __init__(self, db: SQLiteDB):
        self.db = db
        self._init()

    def _init(self) -> None:
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS v5_cloud_clients(
                client_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                platform TEXT NOT NULL,
                app_version TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS v5_cloud_threads(
                thread_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS v5_cloud_messages(
                message_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                client_id TEXT,
                request_id TEXT,
                created_at TEXT NOT NULL
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS v5_cloud_preferences(
                pref_key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    @staticmethod
    def _decode(value: str, default: Any) -> Any:
        try:
            return json.loads(value)
        except Exception:
            return default

    def register_client(
        self,
        *,
        client_id: str | None,
        name: str,
        platform: str,
        app_version: str = "unknown",
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        cid = str(client_id or "").strip()[:128] or new_id("cli_")
        now = utc_now()
        capabilities = [str(x)[:80] for x in (capabilities or []) if str(x).strip()][:64]
        existing = self.db.execute(
            "SELECT created_at FROM v5_cloud_clients WHERE client_id=?",
            (cid,),
            fetch="one",
        )
        created_at = str((existing or {}).get("created_at") or now)
        self.db.execute(
            """INSERT INTO v5_cloud_clients(
                    client_id,name,platform,app_version,capabilities_json,created_at,last_seen,enabled
                ) VALUES(?,?,?,?,?,?,?,1)
                ON CONFLICT(client_id) DO UPDATE SET
                    name=excluded.name,
                    platform=excluded.platform,
                    app_version=excluded.app_version,
                    capabilities_json=excluded.capabilities_json,
                    last_seen=excluded.last_seen,
                    enabled=1""",
            (
                cid,
                (name or "IRAS Client")[:160],
                (platform or "unknown")[:80],
                (app_version or "unknown")[:40],
                self._json(capabilities),
                created_at,
                now,
            ),
        )
        row = self.get_client(cid) or {}
        row["active_thread_id"] = self.active_thread_id()
        return row

    def touch_client(self, client_id: str, *, platform: str = "unknown") -> dict[str, Any]:
        cid = str(client_id or "").strip()[:128]
        if not cid:
            raise ValueError("client_id is required")
        row = self.get_client(cid)
        if row is None:
            return self.register_client(
                client_id=cid,
                name=f"IRAS {platform.title()} Client",
                platform=platform,
            )
        self.db.execute(
            "UPDATE v5_cloud_clients SET last_seen=?,enabled=1 WHERE client_id=?",
            (utc_now(), cid),
        )
        return self.get_client(cid) or {}

    def get_client(self, client_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM v5_cloud_clients WHERE client_id=?",
            (client_id,),
            fetch="one",
        )
        if not row:
            return None
        row["enabled"] = bool(row.get("enabled"))
        row["capabilities"] = self._decode(str(row.pop("capabilities_json", "[]")), [])
        return row

    def list_clients(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT client_id FROM v5_cloud_clients ORDER BY last_seen DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
            fetch="all",
        ) or []
        return [row for x in rows if (row := self.get_client(str(x["client_id"]))) is not None]

    def set_preference(self, key: str, value: Any) -> None:
        pref_key = str(key or "").strip()[:120]
        if not pref_key:
            raise ValueError("preference key is required")
        self.db.execute(
            """INSERT INTO v5_cloud_preferences(pref_key,value_json,updated_at)
               VALUES(?,?,?)
               ON CONFLICT(pref_key) DO UPDATE SET
                   value_json=excluded.value_json,
                   updated_at=excluded.updated_at""",
            (pref_key, self._json(value), utc_now()),
        )

    def get_preference(self, key: str, default: Any = None) -> Any:
        row = self.db.execute(
            "SELECT value_json FROM v5_cloud_preferences WHERE pref_key=?",
            (str(key or "")[:120],),
            fetch="one",
        )
        if not row:
            return default
        return self._decode(str(row.get("value_json") or "null"), default)

    def preferences(self) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT pref_key,value_json FROM v5_cloud_preferences ORDER BY pref_key",
            fetch="all",
        ) or []
        return {
            str(row["pref_key"]): self._decode(str(row.get("value_json") or "null"), None)
            for row in rows
        }

    def create_thread(self, title: str = "New chat", *, thread_id: str | None = None) -> dict[str, Any]:
        tid = str(thread_id or "").strip()[:128] or new_id("thr_")
        now = utc_now()
        self.db.execute(
            """INSERT INTO v5_cloud_threads(thread_id,title,created_at,updated_at,archived)
               VALUES(?,?,?,?,0)
               ON CONFLICT(thread_id) DO NOTHING""",
            (tid, (title or "New chat")[:180], now, now),
        )
        return self.get_thread(tid) or {}

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM v5_cloud_threads WHERE thread_id=?",
            (thread_id,),
            fetch="one",
        )
        if row:
            row["archived"] = bool(row.get("archived"))
        return row

    def list_threads(self, limit: int = 50, *, include_archived: bool = False) -> list[dict[str, Any]]:
        if include_archived:
            rows = self.db.execute(
                "SELECT * FROM v5_cloud_threads ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
                fetch="all",
            ) or []
        else:
            rows = self.db.execute(
                "SELECT * FROM v5_cloud_threads WHERE archived=0 ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
                fetch="all",
            ) or []
        for row in rows:
            row["archived"] = bool(row.get("archived"))
        return rows

    def active_thread_id(self) -> str:
        tid = str(self.get_preference("active_thread_id", "") or "").strip()
        if tid:
            found = self.get_thread(tid)
            if found and not bool(found.get("archived")):
                return tid
        rows = self.list_threads(limit=1)
        if rows:
            tid = str(rows[0]["thread_id"])
        else:
            tid = str(self.create_thread("IRAS Cloud")["thread_id"])
        self.set_preference("active_thread_id", tid)
        return tid

    def ensure_thread(self, thread_id: str | None = None, *, title: str = "IRAS Cloud") -> dict[str, Any]:
        tid = str(thread_id or "").strip()[:128]
        if tid:
            found = self.get_thread(tid)
            if found:
                return found
            return self.create_thread(title=title, thread_id=tid)
        return self.get_thread(self.active_thread_id()) or self.create_thread(title)

    def activate_thread(self, thread_id: str) -> dict[str, Any]:
        thread = self.ensure_thread(thread_id)
        self.set_preference("active_thread_id", thread["thread_id"])
        return thread

    def archive_thread(self, thread_id: str, archived: bool = True) -> dict[str, Any]:
        if not self.get_thread(thread_id):
            raise KeyError(thread_id)
        self.db.execute(
            "UPDATE v5_cloud_threads SET archived=?,updated_at=? WHERE thread_id=?",
            (int(bool(archived)), utc_now(), thread_id),
        )
        if archived and self.active_thread_id() == thread_id:
            self.set_preference("active_thread_id", "")
        return self.get_thread(thread_id) or {}

    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        *,
        client_id: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        thread = self.ensure_thread(thread_id)
        text = str(content or "")
        if not text:
            raise ValueError("message content is required")
        if request_id:
            existing = self.db.execute(
                """SELECT * FROM v5_cloud_messages
                   WHERE thread_id=? AND role=? AND request_id=?
                   ORDER BY created_at DESC LIMIT 1""",
                (thread["thread_id"], str(role or "assistant")[:24], str(request_id)[:128]),
                fetch="one",
            )
            if existing:
                return existing
        mid = new_id("msg_")
        now = utc_now()
        self.db.execute(
            "INSERT INTO v5_cloud_messages VALUES(?,?,?,?,?,?,?)",
            (
                mid,
                thread["thread_id"],
                str(role or "assistant")[:24],
                text,
                (str(client_id)[:128] if client_id else None),
                (str(request_id)[:128] if request_id else None),
                now,
            ),
        )
        self.db.execute(
            "UPDATE v5_cloud_threads SET updated_at=? WHERE thread_id=?",
            (now, thread["thread_id"]),
        )
        # Give the default/new thread a useful title from the first user turn.
        if str(role).lower() == "user" and str(thread.get("title") or "") in {"IRAS Cloud", "New chat"}:
            compact = " ".join(text.split())[:72]
            if compact:
                self.db.execute(
                    "UPDATE v5_cloud_threads SET title=? WHERE thread_id=?",
                    (compact, thread["thread_id"]),
                )
        return {
            "message_id": mid,
            "thread_id": thread["thread_id"],
            "role": str(role or "assistant")[:24],
            "content": text,
            "client_id": client_id,
            "request_id": request_id,
            "created_at": now,
        }

    def messages(self, thread_id: str, limit: int = 100) -> list[dict[str, Any]]:
        count = max(1, min(int(limit), 500))
        rows = self.db.execute(
            """SELECT * FROM v5_cloud_messages WHERE thread_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (thread_id, count),
            fetch="all",
        ) or []
        return list(reversed(rows))

    def snapshot(self, *, thread_id: str | None = None, message_limit: int = 80) -> dict[str, Any]:
        thread = self.ensure_thread(thread_id)
        return {
            "active_thread_id": self.active_thread_id(),
            "thread": thread,
            "threads": self.list_threads(limit=30),
            "messages": self.messages(str(thread["thread_id"]), limit=message_limit),
            "clients": self.list_clients(limit=50),
            "preferences": self.preferences(),
        }
