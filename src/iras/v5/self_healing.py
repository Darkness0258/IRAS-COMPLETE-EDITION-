from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable

from .common import SQLiteDB, EventBus, utc_now


@dataclass
class RecoveryStrategy:
    name: str
    error_class: str
    handler: Callable[[dict[str, Any]], Any]
    max_attempts: int = 1


class SelfHealingEngine:
    def __init__(self, db: SQLiteDB, bus: EventBus | None = None):
        self.db = db
        self.bus = bus or EventBus()
        self.strategies: list[RecoveryStrategy] = []
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS v5_recovery_stats(
            strategy TEXT PRIMARY KEY,
            successes INTEGER NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0,
            last_used TEXT,
            last_error TEXT
        )""")

    def register(self, strategy: RecoveryStrategy) -> None:
        self.strategies.append(strategy)

    def _score(self, name: str) -> float:
        row = self.db.execute("SELECT * FROM v5_recovery_stats WHERE strategy=?", (name,), fetch="one") or {}
        s, f = int(row.get("successes") or 0), int(row.get("failures") or 0)
        return (s + 1) / (s + f + 2)

    def stats(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT strategy,successes,failures,last_used,last_error FROM v5_recovery_stats ORDER BY last_used DESC",
            fetch="all",
        ) or []
        known = {row["strategy"] for row in rows}
        for strategy in self.strategies:
            if strategy.name not in known:
                rows.append({
                    "strategy": strategy.name, "successes": 0, "failures": 0,
                    "last_used": None, "last_error": "",
                })
        for row in rows:
            row["score"] = round(self._score(row["strategy"]), 6)
        return rows

    def recover(self, error: Exception | str, context: dict[str, Any]) -> dict[str, Any]:
        text = f"{type(error).__name__}: {error}" if isinstance(error, Exception) else str(error)
        matches = [s for s in self.strategies if s.error_class == "*" or s.error_class.lower() in text.lower()]
        matches.sort(key=lambda s: self._score(s.name), reverse=True)
        attempts = []
        for strategy in matches:
            for _ in range(max(1, strategy.max_attempts)):
                try:
                    out = strategy.handler(dict(context))
                    self._record(strategy.name, True, "")
                    self.bus.publish("recovery.succeeded", strategy=strategy.name, error=text)
                    return {"recovered": True, "strategy": strategy.name, "result": out, "attempts": attempts + [strategy.name]}
                except Exception as exc:
                    attempts.append(strategy.name)
                    self._record(strategy.name, False, f"{type(exc).__name__}: {exc}")
        self.bus.publish("recovery.failed", error=text, attempts=attempts)
        return {"recovered": False, "attempts": attempts, "error": text}

    def _record(self, name: str, ok: bool, error: str):
        self.db.execute("""
        INSERT INTO v5_recovery_stats(strategy,successes,failures,last_used,last_error)
        VALUES(?,?,?,?,?) ON CONFLICT(strategy) DO UPDATE SET
          successes=successes+excluded.successes,
          failures=failures+excluded.failures,
          last_used=excluded.last_used,last_error=excluded.last_error
        """, (name, int(ok), int(not ok), utc_now(), error[:2000]))
