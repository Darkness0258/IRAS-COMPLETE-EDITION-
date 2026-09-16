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

from iras.remote_access import action_permission, level_for_mode


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

        self.preferred_device_id: str | None = None
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
                error TEXT,
                remote_session_id TEXT,
                permission_level INTEGER NOT NULL DEFAULT 0
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

        # Migrations for stores created before v4. SQLite/PostgreSQL both reject
        # duplicate-column ALTERs; those errors are intentionally ignored.
        for migration in (
            "ALTER TABLE iras_device_commands ADD COLUMN remote_session_id TEXT",
            "ALTER TABLE iras_device_commands ADD COLUMN permission_level INTEGER NOT NULL DEFAULT 0",
        ):
            try:
                self._run(migration)
            except Exception:
                pass

        self._run(
            """
            CREATE TABLE IF NOT EXISTS iras_remote_sessions(
                session_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                mode TEXT NOT NULL,
                max_permission INTEGER NOT NULL,
                scopes TEXT NOT NULL,
                requester_device TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL,
                expires_at DOUBLE PRECISION NOT NULL,
                last_seen DOUBLE PRECISION NOT NULL,
                revoked_at DOUBLE PRECISION
            )
            """
        )

        self._run(
            """
            CREATE INDEX IF NOT EXISTS idx_iras_remote_sessions_device
            ON iras_remote_sessions(device_id, expires_at)
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
        if not device_id and self.preferred_device_id:
            device_id = self.preferred_device_id
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
        remote_session_id: str | None = None,
        permission_level: int | None = None,
    ) -> dict:
        device = self.choose_device(device_id)
        now = self._now()
        command_id = uuid.uuid4().hex
        if permission_level is None:
            permission_level = int(action_permission(action, arguments))
        permission_level = max(0, min(int(permission_level), 3))

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
                expires_at,
                remote_session_id,
                permission_level
            )
            VALUES(?,?,?,?,?,?,?,?,?,?)
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
                str(remote_session_id or "") or None,
                permission_level,
            ),
        )

        return {
            "command_id": command_id,
            "device_id": device["device_id"],
            "device_name": device["display_name"],
            "action": action,
            "status": "queued",
            "remote_session_id": remote_session_id,
            "permission_level": permission_level,
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
                    expires_at,
                    remote_session_id,
                    permission_level
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

    def _scrub_remote_command_payload(self, command_id: str) -> None:
        """Minimize retention of remote command arguments/results after delivery."""
        self._run(
            """
            UPDATE iras_device_commands
            SET arguments='{}', result=NULL
            WHERE command_id=? AND remote_session_id IS NOT NULL
            """,
            (str(command_id),),
        )

    def request_and_wait(
        self,
        *,
        action: str,
        arguments: dict,
        device_id: str | None = None,
        timeout: float = 30.0,
        remote_session_id: str | None = None,
        permission_level: int | None = None,
        requester_device: str = "cloud-agent",
    ):
        queued = self.enqueue(
            action=action,
            arguments=arguments,
            device_id=device_id,
            requester_device=requester_device,
            remote_session_id=remote_session_id,
            permission_level=permission_level,
        )

        completed = self.wait(
            queued["command_id"],
            timeout=timeout,
        )

        status = completed.get(
            "status"
        )

        if status == "succeeded":
            result = completed.get("result")
            if remote_session_id:
                self._scrub_remote_command_payload(queued["command_id"])
            return result

        if status in {
            "queued",
            "claimed",
            "timeout",
        }:
            raise RuntimeError(
                "The computer did not finish the command in time."
            )

        error = completed.get("error") or f"Device command ended with status {status}."
        if remote_session_id:
            self._scrub_remote_command_payload(queued["command_id"])
        raise RuntimeError(error)

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


    def create_remote_session(
        self,
        *,
        device_id: str | None = None,
        mode: str = "control",
        ttl_seconds: int = 1800,
        scopes: list[str] | None = None,
        requester_device: str = "web",
    ) -> dict:
        device = self.choose_device(device_id)
        mode = str(mode or "control").strip().lower()
        level = level_for_mode(mode)
        if level is None or mode == "off":
            raise ValueError("Remote session mode must be read_only, control, or full.")
        ttl_seconds = max(60, min(int(ttl_seconds), 12 * 60 * 60))
        token = uuid.uuid4().hex + uuid.uuid4().hex
        session_id = uuid.uuid4().hex
        now = self._now()
        scopes = [str(item)[:80] for item in (scopes or ["windows"])[:64]]
        self._run(
            """
            INSERT INTO iras_remote_sessions(
                session_id, device_id, token_hash, mode, max_permission,
                scopes, requester_device, created_at, expires_at, last_seen, revoked_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,NULL)
            """,
            (
                session_id,
                device["device_id"],
                self.token_hash(token),
                mode,
                int(level),
                self._json(scopes),
                str(requester_device or "web")[:128],
                now,
                now + ttl_seconds,
                now,
            ),
        )
        return {
            "session_id": session_id,
            "session_token": token,
            "device_id": device["device_id"],
            "device_name": device["display_name"],
            "mode": mode,
            "max_permission": level.name,
            "scopes": scopes,
            "expires_at": now + ttl_seconds,
            "ttl_seconds": ttl_seconds,
        }

    def authorize_remote_session(self, session_id: str, token: str) -> dict | None:
        now = self._now()
        row = self._run(
            """
            SELECT * FROM iras_remote_sessions
            WHERE session_id=? AND revoked_at IS NULL AND expires_at>?
            """,
            (str(session_id), now),
            fetch="one",
        )
        if not row:
            return None
        if not hmac.compare_digest(str(row.get("token_hash") or ""), self.token_hash(token)):
            return None
        self._run(
            "UPDATE iras_remote_sessions SET last_seen=? WHERE session_id=?",
            (now, str(session_id)),
        )
        row.pop("token_hash", None)
        row["scopes"] = self._loads(row.get("scopes"), [])
        row["online_device"] = bool((self.get_device(str(row.get("device_id") or "")) or {}).get("online"))
        return row

    def revoke_remote_session(self, session_id: str) -> bool:
        changed = self._run(
            "UPDATE iras_remote_sessions SET revoked_at=? WHERE session_id=? AND revoked_at IS NULL",
            (self._now(), str(session_id)),
        )
        return bool(changed)

    def list_remote_sessions(self, *, include_expired: bool = False) -> list[dict]:
        now = self._now()
        if include_expired:
            rows = self._run(
                "SELECT * FROM iras_remote_sessions ORDER BY created_at DESC LIMIT 100",
                fetch="all",
            ) or []
        else:
            rows = self._run(
                "SELECT * FROM iras_remote_sessions WHERE revoked_at IS NULL AND expires_at>? ORDER BY created_at DESC LIMIT 100",
                (now,),
                fetch="all",
            ) or []
        for row in rows:
            row.pop("token_hash", None)
            row["scopes"] = self._loads(row.get("scopes"), [])
            row["expired"] = float(row.get("expires_at") or 0) <= now
        return rows

    def remote_request_and_wait(
        self,
        *,
        session: dict,
        action: str,
        arguments: dict,
        timeout: float = 45.0,
        requester_device: str = "remote-client",
    ):
        required = action_permission(action, arguments)
        maximum = int(session.get("max_permission") or 0)
        if int(required) > maximum:
            raise PermissionError(
                f"Remote session mode {session.get('mode')} does not authorize {required.name} action {action!r}."
            )
        queued = self.enqueue(
            action=action,
            arguments=arguments,
            device_id=str(session.get("device_id") or ""),
            requester_device=requester_device,
            ttl_seconds=max(30, min(int(timeout) + 30, 600)),
            remote_session_id=str(session.get("session_id") or ""),
            permission_level=int(required),
        )
        completed = self.wait(queued["command_id"], timeout=timeout)
        if completed.get("status") == "succeeded":
            result = completed.get("result")
            self._scrub_remote_command_payload(queued["command_id"])
            return result
        if completed.get("status") in {"queued", "claimed", "timeout"}:
            raise RuntimeError("The remote laptop did not finish the command in time.")
        error = completed.get("error") or f"Remote command ended with status {completed.get('status')}."
        self._scrub_remote_command_payload(queued["command_id"])
        raise RuntimeError(error)
