from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any

from .common import SQLiteDB, utc_now


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[SQLiteDB], None]


class MigrationManager:
    """Idempotent v5 schema migration ledger for SQLite/PostgreSQL."""

    def __init__(self, db: SQLiteDB):
        self.db = db
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS v5_schema_migrations(
               version INTEGER PRIMARY KEY,name TEXT NOT NULL,applied_at TEXT NOT NULL)"""
        )
        self.migrations = [
            Migration(50001, "rc3-core-indexes", self._core_indexes),
            Migration(50002, "rc3-mobile-delivery-indexes", self._mobile_indexes),
            Migration(50003, "rc3-sync-journal", self._sync_journal),
        ]

    @staticmethod
    def _core_indexes(db: SQLiteDB) -> None:
        for sql in (
            "CREATE INDEX IF NOT EXISTS idx_v5_scheduled_due ON v5_scheduled_jobs(enabled,next_run)",
            "CREATE INDEX IF NOT EXISTS idx_v5_monitors_due ON v5_monitors(enabled,next_check)",
            "CREATE INDEX IF NOT EXISTS idx_v5_memory_namespace ON v5_semantic_memory(namespace,created_at)",
            "CREATE INDEX IF NOT EXISTS idx_v5_notifications_read ON v5_notifications(read,created_at)",
        ):
            db.execute(sql)

    @staticmethod
    def _mobile_indexes(db: SQLiteDB) -> None:
        for sql in (
            "CREATE INDEX IF NOT EXISTS idx_v5_mobile_delivery_pending ON v5_mobile_event_deliveries(mobile_id,delivered)",
            "CREATE INDEX IF NOT EXISTS idx_v5_mobile_approval_status ON v5_mobile_approvals(status,created_at)",
        ):
            db.execute(sql)

    @staticmethod
    def _sync_journal(db: SQLiteDB) -> None:
        db.execute(
            """CREATE TABLE IF NOT EXISTS v5_sync_journal(
               sync_id TEXT PRIMARY KEY,profile_id TEXT NOT NULL,direction TEXT NOT NULL,
               bundle_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,status TEXT NOT NULL)"""
        )

    def applied(self) -> list[dict[str, Any]]:
        return self.db.execute(
            "SELECT version,name,applied_at FROM v5_schema_migrations ORDER BY version",
            fetch="all",
        ) or []

    def apply_all(self) -> dict[str, Any]:
        applied = {int(r["version"]) for r in self.applied()}
        newly: list[int] = []
        for migration in self.migrations:
            if migration.version in applied:
                continue
            migration.apply(self.db)
            self.db.execute(
                "INSERT INTO v5_schema_migrations(version,name,applied_at) VALUES(?,?,?)",
                (migration.version, migration.name, utc_now()),
            )
            newly.append(migration.version)
        return {"current": max([m.version for m in self.migrations], default=0), "applied_now": newly, "history": self.applied()}

    def status(self) -> dict[str, Any]:
        history = self.applied()
        expected = [m.version for m in self.migrations]
        applied = [int(r["version"]) for r in history]
        return {
            "current": max(applied, default=0),
            "target": max(expected, default=0),
            "complete": set(expected) <= set(applied),
            "history": history,
        }
