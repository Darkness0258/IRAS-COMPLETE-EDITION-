from __future__ import annotations

from datetime import datetime, timezone
import threading


class PostgresMemoryStore:
    """PostgreSQL-backed memory for the online IRAS brain."""

    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("DATABASE_URL is required for PostgresMemoryStore.")
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL support requires psycopg. Install IRAS with the cloud extra."
            ) from exc

        self.psycopg = psycopg
        self.dict_row = dict_row
        self.database_url = database_url
        self._lock = threading.RLock()
        self._init()

    def _conn(self):
        return self.psycopg.connect(self.database_url, row_factory=self.dict_row)

    def _init(self):
        with self._conn() as c:
            with c.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS messages(
                        id BIGSERIAL PRIMARY KEY,
                        ts TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS facts(
                        id BIGSERIAL PRIMARY KEY,
                        ts TEXT NOT NULL,
                        key TEXT NOT NULL UNIQUE,
                        value TEXT NOT NULL
                    )
                """)
            c.commit()

    def add_message(self, role, content):
        with self._lock, self._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "INSERT INTO messages(ts, role, content) VALUES(%s,%s,%s)",
                    (self._now(), role, content),
                )
            c.commit()

    def recent_messages(self, limit=20):
        limit = max(1, min(int(limit), 200))
        with self._lock, self._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT role,content FROM messages ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
        return list(reversed(rows))

    def remember(self, key, value):
        with self._lock, self._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO facts(ts,key,value) VALUES(%s,%s,%s)
                    ON CONFLICT(key) DO UPDATE SET ts=EXCLUDED.ts,value=EXCLUDED.value
                    """,
                    (self._now(), key, value),
                )
            c.commit()

    def get_fact(self, key, default=None):
        with self._lock, self._conn() as c:
            with c.cursor() as cur:
                cur.execute("SELECT value FROM facts WHERE key=%s", (key,))
                row = cur.fetchone()
        return row["value"] if row else default

    def search_facts(self, query, limit=10):
        limit = max(1, min(int(limit), 100))
        q = f"%{query}%"
        with self._lock, self._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    """
                    SELECT key,value,ts FROM facts
                    WHERE key ILIKE %s OR value ILIKE %s
                    ORDER BY id DESC LIMIT %s
                    """,
                    (q, q, limit),
                )
                return cur.fetchall()

    def all_facts(self, limit=100):
        limit = max(1, min(int(limit), 500))
        with self._lock, self._conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT key,value,ts FROM facts ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
                return cur.fetchall()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()
