"""People, their faceprints and their voiceprints, kept in the same database as the rest of IRAS.

Only numbers are stored (512 per face sample, 256 per voice sample, packed). No photo
and no recording is ever saved. Face ID and Voice ID tell IRAS who is there, for
greetings and personal answers. They never replace an approval: capability is not authority.
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
VOICE_THRESHOLD = float(os.getenv("IRAS_VOICE_THRESHOLD", "0.50"))  # cosine similarity to a person's average voiceprint
VOICE_MARGIN = 0.06  # the best person must beat the next one by this much
VOICE_SAME = float(os.getenv("IRAS_VOICE_SAME", "0.30"))  # a new teaching clip must sound at least this much like the saved voice
MAX_VOICE_SAMPLES = 12


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pack(vector) -> str:
    import numpy as np

    return base64.b64encode(np.asarray(vector, np.float32).tobytes()).decode("ascii")


def unpack(text: str):
    import numpy as np

    return np.frombuffer(base64.b64decode(text), np.float32)


def _choose(best: dict[str, float], names: dict[str, str], threshold: float, margin: float) -> dict:
    """From one score per person: the match (only if it is clear) and the closest person."""
    ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return {"match": None, "closest": None}
    top_id, top_score = ranked[0]
    closest = {"person_id": top_id, "name": names.get(top_id, ""), "score": round(top_score, 3)}
    second = ranked[1][1] if len(ranked) > 1 else -1.0
    sure = top_score >= threshold and (top_score - second) >= margin
    return {"match": closest if sure else None, "closest": closest}


def decide(vector, samples: list[tuple[str, Any]], names: dict[str, str], threshold: float = THRESHOLD) -> dict:
    """Compare one faceprint with everyone's samples. Returns match (or None) and the closest person."""
    best: dict[str, float] = {}
    for person_id, other in samples:
        score = float(vector @ other)
        if score > best.get(person_id, -1.0):
            best[person_id] = score
    return _choose(best, names, threshold, MARGIN)


def voice_score(vector, vectors: list) -> float:
    """How much one voiceprint sounds like a person: its similarity to the average of their voiceprints."""
    import numpy as np

    centre = np.mean(np.stack(vectors), axis=0)
    norm = float(np.linalg.norm(centre))
    return float(vector @ (centre / norm)) if norm > 1e-9 else -1.0


def decide_voice(vector, samples: list[tuple[str, Any]], names: dict[str, str], threshold: float = VOICE_THRESHOLD) -> dict:
    """Compare one voiceprint with each person's average voiceprint. Returns match (or None) and the closest person."""
    groups: dict[str, list] = {}
    for person_id, other in samples:
        groups.setdefault(person_id, []).append(other)
    return _choose({pid: voice_score(vector, vecs) for pid, vecs in groups.items()}, names, threshold, VOICE_MARGIN)


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
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS identity_voices ("
            "voice_id TEXT PRIMARY KEY, person_id TEXT NOT NULL, embedding TEXT NOT NULL, created_at TEXT NOT NULL)"
        )

    def add_person(self, name: str) -> dict:
        name = " ".join(str(name or "").split())[:60]
        if not name:
            raise ValueError("Write a name first.")
        person = {"person_id": "per_" + uuid.uuid4().hex[:12], "name": name, "created_at": _now(), "faces": 0, "voices": 0}
        self.db.execute(
            "INSERT INTO identity_people (person_id, name, created_at) VALUES (?,?,?)",
            (person["person_id"], person["name"], person["created_at"]),
        )
        return person

    def people(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT p.person_id, p.name, p.created_at, "
            "(SELECT COUNT(*) FROM identity_faces f WHERE f.person_id = p.person_id) AS faces, "
            "(SELECT COUNT(*) FROM identity_voices v WHERE v.person_id = p.person_id) AS voices "
            "FROM identity_people p ORDER BY p.created_at",
            fetch="all",
        ) or []
        return [{**dict(r), "faces": int(dict(r).get("faces") or 0), "voices": int(dict(r).get("voices") or 0)} for r in rows]

    def person(self, person_id: str) -> dict | None:
        row = self.db.execute("SELECT person_id, name FROM identity_people WHERE person_id=?", (person_id,), fetch="one")
        return dict(row) if row else None

    def find_by_name(self, name: str) -> dict | None:
        wanted = " ".join(str(name or "").split()).lower()
        return next((p for p in self.people() if p["name"].lower() == wanted), None)

    def delete_person(self, person_id: str) -> None:
        """Forget a person completely: every faceprint, every voiceprint, the name."""
        self.db.execute("DELETE FROM identity_faces WHERE person_id=?", (person_id,))
        self.db.execute("DELETE FROM identity_voices WHERE person_id=?", (person_id,))
        self.db.execute("DELETE FROM identity_people WHERE person_id=?", (person_id,))

    def _drop_if_empty(self, person_id: str) -> None:
        left = next((p for p in self.people() if p["person_id"] == person_id), None)
        if left is not None and not left["faces"] and not left["voices"]:
            self.db.execute("DELETE FROM identity_people WHERE person_id=?", (person_id,))

    def forget_face(self, person_id: str) -> None:
        """Forget only the face. The person stays if their voice is still known."""
        self.db.execute("DELETE FROM identity_faces WHERE person_id=?", (person_id,))
        self._drop_if_empty(person_id)

    def forget_voice(self, person_id: str) -> None:
        """Forget only the voice. The person stays if their face is still known."""
        self.db.execute("DELETE FROM identity_voices WHERE person_id=?", (person_id,))
        self._drop_if_empty(person_id)

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

    def add_voice(self, person_id: str, vector) -> int:
        """Save one voice sample. Keeps the newest MAX_VOICE_SAMPLES. Returns how many samples the person has."""
        self.db.execute(
            "INSERT INTO identity_voices (voice_id, person_id, embedding, created_at) VALUES (?,?,?,?)",
            ("vc_" + uuid.uuid4().hex[:14], person_id, pack(vector), _now()),
        )
        rows = self.db.execute(
            "SELECT voice_id FROM identity_voices WHERE person_id=? ORDER BY created_at DESC", (person_id,), fetch="all"
        ) or []
        for old in rows[MAX_VOICE_SAMPLES:]:
            self.db.execute("DELETE FROM identity_voices WHERE voice_id=?", (dict(old)["voice_id"],))
        return min(len(rows), MAX_VOICE_SAMPLES)

    def voice_samples(self) -> list[tuple[str, Any]]:
        rows = self.db.execute("SELECT person_id, embedding FROM identity_voices", fetch="all") or []
        return [(dict(r)["person_id"], unpack(dict(r)["embedding"])) for r in rows]

    def voices_of(self, person_id: str) -> list:
        rows = self.db.execute("SELECT embedding FROM identity_voices WHERE person_id=?", (person_id,), fetch="all") or []
        return [unpack(dict(r)["embedding"]) for r in rows]
