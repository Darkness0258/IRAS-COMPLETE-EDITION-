from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import hmac
import json
import sqlite3
import threading
import time
import uuid


class DeviceBridgeStore:
    """Persistent device registry + command queue.

    PostgreSQL is used on Render/Supabase. SQLite is used for local tests and
    local cloud development. Device secrets are stored only as SHA-256 hashes.
    """

    def __init__(
        self,
        database_url: str = "",
        sqlite_path: str | Path | None = None,
    ):
        self.database_url = str(database_url or "").strip()
        self.sqlite_path = Path(
            sqlite_path
            or "data/device_bridge.db"
        ).expanduser()

        self._lock = threading.RLock()
        self._connection = None
        self._postgres = bool(self.database_url)
        self.psycopg = None
        self.dict_row = None

        if self._postgres:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError(
                    "Device bridge PostgreSQL support requires psycopg."
                ) from exc

            self.psycopg = psycopg
            self.dict_row = dict_row
        else:
            self.sqlite_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

        self._init()

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(
            str(token).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _json(value) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _loads(value, default):
        if value in (None, ""):
            return default
        try:
            return json.loads(value)
        except Exception:
            return default

    @staticmethod
    def _now() -> float:
        return time.time()

    def _new_connection(self):
        if self._postgres:
            return self.psycopg.connect(
                self.database_url,
                row_factory=self.dict_row,
                autocommit=True,
                connect_timeout=10,
            )

        connection = sqlite3.connect(
            self.sqlite_path,
            check_same_thread=False,
            timeout=10,
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_connection(self):
        if self._connection is None:
            self._connection = self._new_connection()
            return self._connection

        if self._postgres and self._connection.closed:
            self._connection = self._new_connection()

        return self._connection

    def _drop_connection(self):
        connection = self._connection
        self._connection = None

        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    def _sql(self, text: str) -> str:
        if self._postgres:
            return text.replace("?", "%s")
        return text

    def _run(
        self,
        sql: str,
        params=(),
        *,
        fetch: str | None = None,
    ):
        sql = self._sql(sql)

        with self._lock:
            attempts = 2 if self._postgres else 1

            for attempt in range(attempts):
                try:
                    connection = self._ensure_connection()
                    cursor = connection.cursor()

                    try:
                        cursor.execute(sql, params)

                        if fetch == "one":
                            row = cursor.fetchone()
                            return dict(row) if row else None

                        if fetch == "all":
                            rows = cursor.fetchall()
                            return [dict(row) for row in rows]

                        if not self._postgres:
                            connection.commit()

                        return cursor.rowcount
                    finally:
                        cursor.close()

                except Exception as exc:
                    if (
                        self._postgres
                        and isinstance(
                            exc,
                            (
                                self.psycopg.OperationalError,
                                self.psycopg.InterfaceError,
                            ),
                        )
                        and attempt == 0
                    ):
                        self._drop_connection()
                        continue
                    raise

        return None

    def _init(self):
        self._run(
            """
            CREATE TABLE IF NOT EXISTS iras_devices(
                device_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                platform TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                capabilities TEXT NOT NULL,
                app_version TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at DOUBLE PRECISION NOT NULL,
                last_seen DOUBLE PRECISION NOT NULL
            )
            """
        )

        self._run(
            """
            CREATE TABLE IF NOT EXISTS iras_device_commands(
                command_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                action TEXT NOT NULL,
                arguments TEXT NOT NULL,
                status TEXT NOT NULL,
                requester_device TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL,
                expires_at DOUBLE PRECISION NOT NULL,
                claimed_at DOUBLE PRECISION,
                completed_at DOUBLE PRECISION,
                result TEXT,
                error TEXT
            )
            """
        )

        self._run(
            """
            CREATE INDEX IF NOT EXISTS
            idx_iras_device_commands_queue
            ON iras_device_commands(
                device_id,
                status,
                created_at
            )
            """
        )

    def pair_device(
        self,
        *,
        device_id: str,
        display_name: str,
        platform: str,
        device_token: str,
        capabilities: list[str],
        app_version: str,
    ) -> dict:
        now = self._now()

        self._run(
            """
            INSERT INTO iras_devices(
                device_id,
                display_name,
                platform,
                token_hash,
                capabilities,
                app_version,
                enabled,
                created_at,
                last_seen
            )
            VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(device_id)
            DO UPDATE SET
                display_name=excluded.display_name,
                platform=excluded.platform,
                token_hash=excluded.token_hash,
                capabilities=excluded.capabilities,
                app_version=excluded.app_version,
                enabled=1,
                last_seen=excluded.last_seen
            """,
            (
                device_id,
                display_name[:128],
                platform[:64],
                self.token_hash(device_token),
                self._json(capabilities),
                app_version[:32],
                1,
                now,
                now,
            ),
        )

        return self.get_device(device_id) or {}

    def authorize_device(
        self,
        device_id: str,
        device_token: str,
    ) -> bool:
        row = self._run(
            """
            SELECT token_hash, enabled
            FROM iras_devices
            WHERE device_id=?
            """,
            (device_id,),
            fetch="one",
        )

        if not row or not bool(row["enabled"]):
            return False

        supplied = self.token_hash(device_token)

        return hmac.compare_digest(
            str(row["token_hash"]),
            supplied,
        )

    def touch_device(self, device_id: str) -> None:
        self._run(
            """
            UPDATE iras_devices
            SET last_seen=?
            WHERE device_id=?
            """,
            (
                self._now(),
                device_id,
            ),
        )

    def get_device(self, device_id: str) -> dict | None:
        row = self._run(
            """
            SELECT
                device_id,
                display_name,
                platform,
                capabilities,
                app_version,
                enabled,
                created_at,
                last_seen
            FROM iras_devices
            WHERE device_id=?
            """,
            (device_id,),
            fetch="one",
        )

        if not row:
            return None

        row["capabilities"] = self._loads(
            row.get("capabilities"),
            [],
        )
        row["enabled"] = bool(row["enabled"])
        row["online"] = (
            bool(row["enabled"])
            and (
                self._now()
                - float(row["last_seen"])
            ) <= 65
        )
        return row

    def list_devices(self) -> list[dict]:
        rows = self._run(
            """
            SELECT
                device_id,
                display_name,
                platform,
                capabilities,
                app_version,
                enabled,
                created_at,
                last_seen
            FROM iras_devices
            ORDER BY last_seen DESC
            """,
            fetch="all",
        ) or []

        now = self._now()

        for row in rows:
            row["capabilities"] = self._loads(
                row.get("capabilities"),
                [],
            )
            row["enabled"] = bool(row["enabled"])
            row["online"] = (
                bool(row["enabled"])
                and (
                    now
                    - float(row["last_seen"])
                ) <= 65
            )

        return rows

    def choose_device(
        self,
        device_id: str | None = None,
    ) -> dict:
        if device_id:
            device = self.get_device(device_id)

            if not device:
                raise RuntimeError(
                    f"Unknown IRAS device: {device_id}"
                )

            if not device["online"]:
                raise RuntimeError(
                    f"IRAS device '{device['display_name']}' is offline."
                )

            return device

        online = [
            item
            for item in self.list_devices()
            if item.get("online")
        ]

        if not online:
            raise RuntimeError(
                "No paired IRAS computer is online."
            )

        windows = [
            item
            for item in online
            if "windows" in str(
                item.get("platform", "")
            ).lower()
        ]

        return (
            windows[0]
            if windows
            else online[0]
        )

    def enqueue(
        self,
        *,
        action: str,
        arguments: dict,
        device_id: str | None = None,
        requester_device: str = "cloud-agent",
        ttl_seconds: int = 120,
    ) -> dict:
        device = self.choose_device(device_id)
        now = self._now()
        command_id = uuid.uuid4().hex

        self._run(
            """
            INSERT INTO iras_device_commands(
                command_id,
                device_id,
                action,
                arguments,
                status,
                requester_device,
                created_at,
                expires_at
            )
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                command_id,
                device["device_id"],
                action,
                self._json(arguments),
                "queued",
                requester_device[:128],
                now,
                now + max(
                    15,
                    min(
                        int(ttl_seconds),
                        600,
                    ),
                ),
            ),
        )

        return {
            "command_id": command_id,
            "device_id": device["device_id"],
            "device_name": device["display_name"],
            "action": action,
            "status": "queued",
        }

    def claim_next(
        self,
        device_id: str,
    ) -> dict | None:
        now = self._now()

        self._run(
            """
            UPDATE iras_device_commands
            SET status='expired',
                completed_at=?
            WHERE
                device_id=?
                AND status='queued'
                AND expires_at<=?
            """,
            (
                now,
                device_id,
                now,
            ),
        )

        for _ in range(4):
            row = self._run(
                """
                SELECT
                    command_id,
                    device_id,
                    action,
                    arguments,
                    status,
                    created_at,
                    expires_at
                FROM iras_device_commands
                WHERE
                    device_id=?
                    AND status='queued'
                    AND expires_at>?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (
                    device_id,
                    now,
                ),
                fetch="one",
            )

            if not row:
                return None

            changed = self._run(
                """
                UPDATE iras_device_commands
                SET status='claimed',
                    claimed_at=?
                WHERE
                    command_id=?
                    AND status='queued'
                """,
                (
                    now,
                    row["command_id"],
                ),
            )

            if changed == 1:
                row["status"] = "claimed"
                row["arguments"] = self._loads(
                    row.get("arguments"),
                    {},
                )
                return row

        return None

    def complete(
        self,
        *,
        command_id: str,
        device_id: str,
        ok: bool,
        result=None,
        error: str = "",
    ) -> dict:
        status = (
            "succeeded"
            if ok
            else "failed"
        )

        changed = self._run(
            """
            UPDATE iras_device_commands
            SET
                status=?,
                completed_at=?,
                result=?,
                error=?
            WHERE
                command_id=?
                AND device_id=?
                AND status='claimed'
            """,
            (
                status,
                self._now(),
                self._json(result),
                str(error or "")[:8000],
                command_id,
                device_id,
            ),
        )

        if changed != 1:
            raise RuntimeError(
                "Command is not claimable/completable by this device."
            )

        return (
            self.get_command(command_id)
            or {}
        )

    def get_command(
        self,
        command_id: str,
    ) -> dict | None:
        row = self._run(
            """
            SELECT *
            FROM iras_device_commands
            WHERE command_id=?
            """,
            (command_id,),
            fetch="one",
        )

        if not row:
            return None

        row["arguments"] = self._loads(
            row.get("arguments"),
            {},
        )
        row["result"] = self._loads(
            row.get("result"),
            None,
        )
        return row

    def wait(
        self,
        command_id: str,
        timeout: float = 30.0,
    ) -> dict:
        deadline = (
            time.monotonic()
            + max(
                1.0,
                min(
                    float(timeout),
                    90.0,
                ),
            )
        )

        while time.monotonic() < deadline:
            command = self.get_command(
                command_id
            )

            if not command:
                raise RuntimeError(
                    "Device command disappeared."
                )

            if command["status"] in {
                "succeeded",
                "failed",
                "expired",
            }:
                return command

            time.sleep(0.20)

        return (
            self.get_command(command_id)
            or {
                "command_id": command_id,
                "status": "timeout",
            }
        )

    def request_and_wait(
        self,
        *,
        action: str,
        arguments: dict,
        device_id: str | None = None,
        timeout: float = 30.0,
    ):
        queued = self.enqueue(
            action=action,
            arguments=arguments,
            device_id=device_id,
        )

        completed = self.wait(
            queued["command_id"],
            timeout=timeout,
        )

        status = completed.get(
            "status"
        )

        if status == "succeeded":
            return completed.get(
                "result"
            )

        if status in {
            "queued",
            "claimed",
            "timeout",
        }:
            raise RuntimeError(
                "The computer did not finish the command in time."
            )

        raise RuntimeError(
            completed.get("error")
            or f"Device command ended with status {status}."
        )

    def recent_commands(
        self,
        device_id: str,
        limit: int = 20,
    ) -> list[dict]:
        limit = max(
            1,
            min(
                int(limit),
                100,
            ),
        )

        rows = self._run(
            """
            SELECT *
            FROM iras_device_commands
            WHERE device_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (
                device_id,
                limit,
            ),
            fetch="all",
        ) or []

        for row in rows:
            row["arguments"] = self._loads(
                row.get("arguments"),
                {},
            )
            row["result"] = self._loads(
                row.get("result"),
                None,
            )

        return rows

    def close(self):
        with self._lock:
            self._drop_connection()
