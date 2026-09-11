from __future__ import annotations

from datetime import datetime, timezone
import threading


class PostgresMemoryStore:
    """
    PostgreSQL-backed memory for the online IRAS brain.

    Important latency behavior:
    A single persistent psycopg connection is reused instead of opening a
    brand-new TLS/database connection for every memory read/write.

    If Supabase closes the connection while Render is idle, the next query
    reconnects automatically once and continues normally.
    """

    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError(
                "DATABASE_URL is required for PostgresMemoryStore."
            )

        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL support requires psycopg. "
                "Install IRAS with the cloud extra."
            ) from exc

        self.psycopg = psycopg
        self.dict_row = dict_row
        self.database_url = database_url

        # IRAS cloud serializes its agent loop, but this lock also makes
        # the store safe if other API endpoints access memory concurrently.
        self._lock = threading.RLock()
        self._connection = None

        self._init()

    def _new_connection(self):
        return self.psycopg.connect(
            self.database_url,
            row_factory=self.dict_row,
            autocommit=True,
            connect_timeout=10,
        )

    def _ensure_connection(self):
        if (
            self._connection is None
            or self._connection.closed
        ):
            self._connection = self._new_connection()

        return self._connection

    def _drop_connection(self) -> None:
        connection = self._connection
        self._connection = None

        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    def _run(
        self,
        sql: str,
        params=None,
        *,
        fetch: str | None = None,
    ):
        """
        Execute using the persistent connection.

        Retry exactly once on connection-level failure. We intentionally
        do not retry arbitrary SQL/programming errors.
        """
        params = params or ()

        with self._lock:
            for attempt in range(2):
                try:
                    connection = self._ensure_connection()

                    with connection.cursor() as cur:
                        cur.execute(sql, params)

                        if fetch == "one":
                            return cur.fetchone()

                        if fetch == "all":
                            return cur.fetchall()

                        return None

                except (
                    self.psycopg.OperationalError,
                    self.psycopg.InterfaceError,
                ):
                    self._drop_connection()

                    if attempt == 0:
                        print(
                            "[IRAS DB] Supabase connection was stale; "
                            "reconnecting once.",
                            flush=True,
                        )
                        continue

                    raise

        return None

    def _init(self):
        self._run(
            """
            CREATE TABLE IF NOT EXISTS messages(
                id BIGSERIAL PRIMARY KEY,
                ts TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL
            )
            """
        )

        self._run(
            """
            CREATE TABLE IF NOT EXISTS facts(
                id BIGSERIAL PRIMARY KEY,
                ts TEXT NOT NULL,
                key TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL
            )
            """
        )

    def add_message(self, role, content):
        self._run(
            "INSERT INTO messages(ts, role, content) "
            "VALUES(%s,%s,%s)",
            (
                self._now(),
                role,
                content,
            ),
        )

    def recent_messages(self, limit=20):
        limit = max(
            1,
            min(int(limit), 200),
        )

        rows = self._run(
            "SELECT role,content "
            "FROM messages "
            "ORDER BY id DESC "
            "LIMIT %s",
            (limit,),
            fetch="all",
        )

        return list(
            reversed(rows or [])
        )

    def remember(self, key, value):
        self._run(
            """
            INSERT INTO facts(ts,key,value)
            VALUES(%s,%s,%s)
            ON CONFLICT(key)
            DO UPDATE SET
                ts=EXCLUDED.ts,
                value=EXCLUDED.value
            """,
            (
                self._now(),
                key,
                value,
            ),
        )

    def get_fact(
        self,
        key,
        default=None,
    ):
        row = self._run(
            "SELECT value "
            "FROM facts "
            "WHERE key=%s",
            (key,),
            fetch="one",
        )

        return (
            row["value"]
            if row
            else default
        )

    def search_facts(
        self,
        query,
        limit=10,
    ):
        limit = max(
            1,
            min(int(limit), 100),
        )

        q = f"%{query}%"

        return (
            self._run(
                """
                SELECT key,value,ts
                FROM facts
                WHERE
                    key ILIKE %s
                    OR value ILIKE %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (
                    q,
                    q,
                    limit,
                ),
                fetch="all",
            )
            or []
        )

    def all_facts(
        self,
        limit=100,
    ):
        limit = max(
            1,
            min(int(limit), 500),
        )

        return (
            self._run(
                "SELECT key,value,ts "
                "FROM facts "
                "ORDER BY id DESC "
                "LIMIT %s",
                (limit,),
                fetch="all",
            )
            or []
        )

    def close(self) -> None:
        with self._lock:
            self._drop_connection()

    @staticmethod
    def _now():
        return (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )
