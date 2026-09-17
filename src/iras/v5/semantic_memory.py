from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any

from .common import SQLiteDB, new_id, utc_now

_TOKEN = re.compile(r"[A-Za-z0-9_\-]{2,}")


def _tokens(text: str) -> Counter:
    return Counter(t.lower() for t in _TOKEN.findall(text))


def _similarity(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


class SemanticMemory:
    """Dependency-light semantic-ish durable memory with project/tag namespaces.

    It intentionally uses transparent lexical vectors instead of silently
    downloading an embedding model. An embedding backend can be plugged in later.
    """

    def __init__(self, db: SQLiteDB):
        self.db = db
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS v5_semantic_memory(
            memory_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            namespace TEXT NOT NULL,
            kind TEXT NOT NULL,
            text TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )""")

    def remember(self, text: str, *, namespace: str = "default", kind: str = "note", metadata: dict[str, Any] | None = None) -> str:
        mid = new_id("mem_")
        self.db.execute(
            "INSERT INTO v5_semantic_memory(memory_id,created_at,namespace,kind,text,metadata_json) VALUES(?,?,?,?,?,?)",
            (mid, utc_now(), namespace, kind, text[:50000], json.dumps(metadata or {}, ensure_ascii=False)),
        )
        return mid

    def search(self, query: str, *, namespace: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        if namespace:
            rows = self.db.execute("SELECT * FROM v5_semantic_memory WHERE namespace=?", (namespace,), fetch="all") or []
        else:
            rows = self.db.execute("SELECT * FROM v5_semantic_memory", fetch="all") or []
        qv = _tokens(query)
        ranked = []
        for row in rows:
            score = _similarity(qv, _tokens(row["text"] + " " + row["kind"]))
            if score > 0:
                row["metadata"] = json.loads(row.pop("metadata_json"))
                row["score"] = round(score, 6)
                ranked.append(row)
        ranked.sort(key=lambda r: (r["score"], r["created_at"]), reverse=True)
        return ranked[:max(1, limit)]
