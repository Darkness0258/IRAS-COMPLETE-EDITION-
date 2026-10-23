"""People and their faceprints, kept in the same database as the rest of IRAS.

Only numbers are stored (512 per sample, packed). No photo is ever saved.
Face ID tells IRAS who is there, for greetings and personal answers. It never
replaces an approval: capability is not authority.
"""
from __future__ import annotations

import base64
import os
import uuid
from datetime import datetime, timezone
from typing import Any

THRESHOLD = float(os.getenv("IRAS_FACE_THRESHOLD", "0.45"))  # cosine similarity needed to say "that is you"
MARGIN = 0.05  # the best person must beat the next one by this much
MIN_TURN = float(os.getenv("IRAS_FACE_MIN_TURN", "0.30"))  # head-turn needed for the liveness check
MAX_SAMPLES = 12


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pack(vector) -> str:
    import numpy as np

    return base64.b64encode(np.asarray(vector, np.float32).tobytes()).decode("ascii")


def unpack(text: str):
    import numpy as np

    return np.frombuffer(base64.b64decode(text), np.float32)


def decide(vector, samples: list[tuple[str, Any]], names: dict[str, str], threshold: float = THRESHOLD) -> dict:
    """Compare one faceprint with everyone's samples. Returns match (or None) and the closest person."""
    best: dict[str, float] = {}
    for person_id, other in samples:
        score = float(vector @ other)
        if score > best.get(person_id, -1.0):
            best[person_id] = score
    ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return {"match": None, "closest": None}
    top_id, top_score = ranked[0]
    closest = {"person_id": top_id, "name": names.get(top_id, ""), "score": round(top_score, 3)}
    second = ranked[1][1] if len(ranked) > 1 else -1.0
    sure = top_score >= threshold and (top_score - second) >= MARGIN
    return {"match": closest if sure else None, "closest": closest}


def check_liveness(turns: list[float], min_turn: float = MIN_TURN) -> dict:
    """Basic check: a real head turns from side to side across the frames; a flat photo held still does not."""
    if len(turns) < 3:
        return {"checked": False, "passed": False, "turn": 0.0}
    spread = max(turns) - min(turns)
    return {"checked": True, "passed": spread >= min_turn, "turn": round(spread, 2)}


class IdentityStore:
    def __init__(self, db) -> None:
        self.db = db
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS identity_people ("
            "person_id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS identity_faces ("
            "face_id TEXT PRIMARY KEY, person_id TEXT NOT NULL, embedding TEXT NOT NULL, created_at TEXT NOT NULL)"
        )

    def add_person(self, name: str) -> dict:
        name = " ".join(str(name or "").split())[:60]
        if not name:
            raise ValueError("Write a name first.")
        person = {"person_id": "per_" + uuid.uuid4().hex[:12], "name": name, "created_at": _now(), "faces": 0}
        self.db.execute(
            "INSERT INTO identity_people (person_id, name, created_at) VALUES (?,?,?)",
            (person["person_id"], person["name"], person["created_at"]),
        )
        return person

    def people(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT p.person_id, p.name, p.created_at, "
            "(SELECT COUNT(*) FROM identity_faces f WHERE f.person_id = p.person_id) AS faces "
            "FROM identity_people p ORDER BY p.created_at",
            fetch="all",
        ) or []
        return [{**dict(r), "faces": int(dict(r).get("faces") or 0)} for r in rows]

    def person(self, person_id: str) -> dict | None:
        row = self.db.execute("SELECT person_id, name FROM identity_people WHERE person_id=?", (person_id,), fetch="one")
        return dict(row) if row else None

    def find_by_name(self, name: str) -> dict | None:
        wanted = " ".join(str(name or "").split()).lower()
        return next((p for p in self.people() if p["name"].lower() == wanted), None)

    def delete_person(self, person_id: str) -> None:
        self.db.execute("DELETE FROM identity_faces WHERE person_id=?", (person_id,))
        self.db.execute("DELETE FROM identity_people WHERE person_id=?", (person_id,))

    def add_face(self, person_id: str, vector) -> int:
        """Save one sample. Keeps the newest MAX_SAMPLES. Returns how many samples the person has."""
        self.db.execute(
            "INSERT INTO identity_faces (face_id, person_id, embedding, created_at) VALUES (?,?,?,?)",
            ("fc_" + uuid.uuid4().hex[:14], person_id, pack(vector), _now()),
        )
        rows = self.db.execute(
            "SELECT face_id FROM identity_faces WHERE person_id=? ORDER BY created_at DESC", (person_id,), fetch="all"
        ) or []
        for old in rows[MAX_SAMPLES:]:
            self.db.execute("DELETE FROM identity_faces WHERE face_id=?", (dict(old)["face_id"],))
        return min(len(rows), MAX_SAMPLES)

    def samples(self) -> list[tuple[str, Any]]:
        rows = self.db.execute("SELECT person_id, embedding FROM identity_faces", fetch="all") or []
        return [(dict(r)["person_id"], unpack(dict(r)["embedding"])) for r in rows]

    def names(self) -> dict[str, str]:
        return {p["person_id"]: p["name"] for p in self.people()}
