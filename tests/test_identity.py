import sqlite3

import numpy as np
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from iras.identity import routes, store as ids
from iras.identity.face import Face


class FakeDB:
    """Same call style as the project's SQLiteDB: execute(sql, params, fetch=None|"one"|"all")."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql, params=(), fetch=None):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        if fetch == "one":
            row = cur.fetchone()
            return dict(row) if row else None
        if fetch == "all":
            return [dict(r) for r in cur.fetchall()]
        return None


def unit(seed):
    v = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def near(vec, noise, seed):
    v = vec + np.random.default_rng(seed).normal(scale=noise, size=512).astype(np.float32)
    return v / np.linalg.norm(v)


def test_packing_round_trip():
    v = unit(1)
    assert np.allclose(ids.unpack(ids.pack(v)), v)


def test_decide_knows_people_and_refuses_strangers():
    alice, bob = unit(1), unit(2)
    samples = [("a", alice), ("a", near(alice, 0.01, 3)), ("b", bob)]
    names = {"a": "Alice", "b": "Bob"}
    hit = ids.decide(near(alice, 0.01, 4), samples, names)
    assert hit["match"]["name"] == "Alice" and hit["match"]["score"] > 0.9
    stranger = ids.decide(unit(99), samples, names)
    assert stranger["match"] is None and stranger["closest"] is not None
    assert ids.decide(alice, [], {}) == {"match": None, "closest": None}


def test_two_look_alikes_are_not_guessed():
    base = unit(5)
    twin_a, twin_b = near(base, 0.01, 6), near(base, 0.01, 7)
    out = ids.decide(base, [("a", twin_a), ("b", twin_b)], {"a": "A", "b": "B"})
    assert out["match"] is None  # too close to call, so she asks instead of guessing


def test_liveness_needs_a_head_turn():
    assert ids.check_liveness([0.02, 0.03, 0.01, 0.02])["passed"] is False
    assert ids.check_liveness([-0.3, -0.1, 0.1, 0.3])["passed"] is True
    assert ids.check_liveness([0.0, 0.5]) == {"checked": False, "passed": False, "turn": 0.0}


def test_store_people_samples_and_forgetting():
    s = ids.IdentityStore(FakeDB())
    p = s.add_person("  Hamza  ")
    assert p["name"] == "Hamza" and s.find_by_name("hamza")["person_id"] == p["person_id"]
    for i in range(ids.MAX_SAMPLES + 3):
        count = s.add_face(p["person_id"], unit(i))
    assert count == ids.MAX_SAMPLES
    assert s.people()[0]["faces"] == ids.MAX_SAMPLES and len(s.samples()) == ids.MAX_SAMPLES
    s.delete_person(p["person_id"])
    assert s.people() == [] and s.samples() == []
    with pytest.raises(ValueError):
        s.add_person("   ")


class FakeEngine:
    """Stands in for the real models: the 'picture' is just a name."""

    people = {b"alice": unit(10), b"bob": unit(20)}

    def tools_missing(self):
        return ""

    def models_ready(self):
        return True

    def _face(self, turn=0.0):
        return Face((0, 0, 100, 100), 0.9, [[30, 40], [70, 40], [50 + turn * 40, 60], [35, 80], [65, 80]])

    def analyze(self, data):
        name, _, turn = data.partition(b"@")
        if name not in self.people:
            return [], None
        return [self._face(float(turn or 0))], self.people[name]

    def one_face(self, data):
        faces, vec = self.analyze(data)
        if not faces:
            from iras.identity.face import FaceError
            raise FaceError("I cannot see a face. Face the camera in good light.")
        return faces[0], vec


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(routes, "engine", lambda: FakeEngine())
    app = FastAPI()

    def authorize(header):
        if header != "Bearer ok":
            raise HTTPException(status_code=401, detail="no")

    routes.register_identity_routes(app, authorize, FakeDB)
    c = TestClient(app)
    c.headers.update({"Authorization": "Bearer ok"})
    return c


def img(name):
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(name).decode()


def test_the_token_is_required(client):
    assert client.get("/v1/identity/people", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_enroll_then_recognise_then_forget(client):
    assert client.get("/v1/identity/status").json()["available"] is True
    for _ in range(3):
        r = client.post("/v1/identity/face/enroll", json={"name": "Alice", "image": img(b"alice")})
        assert r.status_code == 200
    assert r.json()["samples"] == 3
    client.post("/v1/identity/face/enroll", json={"name": "Bob", "image": img(b"bob")})
    people = client.get("/v1/identity/people").json()["people"]
    assert sorted(p["name"] for p in people) == ["Alice", "Bob"]

    who = client.post("/v1/identity/face/verify", json={"image": img(b"alice")}).json()
    assert who["match"]["name"] == "Alice" and who["liveness"] is None

    still = [img(b"alice@0.0")] * 4
    turning = [img(b"alice@-0.4"), img(b"alice@-0.1"), img(b"alice@0.2"), img(b"alice@0.4")]
    blocked = client.post("/v1/identity/face/verify", json={"image": img(b"alice"), "frames": still, "require_liveness": True}).json()
    assert blocked["match"] is None and "Turn your head" in blocked["message"]
    passed = client.post("/v1/identity/face/verify", json={"image": img(b"alice"), "frames": turning, "require_liveness": True}).json()
    assert passed["match"]["name"] == "Alice" and passed["liveness"]["passed"] is True

    nobody = client.post("/v1/identity/face/verify", json={"image": img(b"nobody")}).json()
    assert nobody["faces"] == 0 and nobody["match"] is None

    alice_id = next(p["person_id"] for p in people if p["name"] == "Alice")
    assert client.delete(f"/v1/identity/people/{alice_id}").status_code == 200
    gone = client.post("/v1/identity/face/verify", json={"image": img(b"alice")}).json()
    assert gone["match"] is None


def test_enroll_errors_are_plain(client):
    r = client.post("/v1/identity/face/enroll", json={"image": img(b"alice")})
    assert r.status_code == 422 and "who this is" in r.json()["detail"]
    r = client.post("/v1/identity/face/enroll", json={"name": "X", "image": img(b"nobody")})
    assert r.status_code == 422 and "cannot see a face" in r.json()["detail"]
