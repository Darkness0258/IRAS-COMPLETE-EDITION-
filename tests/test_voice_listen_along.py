"""Voice check while you talk to her: the server side.

The screen records a few seconds while she listens, sends them to /v1/identity/voice/verify, and reads
one new word in the answer, `verdict`. These tests cover that word (match, other, unsure, nobody,
unheard) and prove the old answer did not change. They use made-up voices: no model, no internet.
The screen's side is in test_command_center_listen_along.py and the real-browser test.
"""
import base64
import sqlite3

import numpy as np
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from iras.identity import routes, store as ids, voice as V


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


def unit(seed, size=256):
    v = np.random.default_rng(seed).normal(size=size).astype(np.float32)
    return v / np.linalg.norm(v)


def like(a, likeness, seed):
    """A voice whose similarity to `a` is exactly `likeness` (a number from 0 to 1)."""
    other = unit(seed, len(a))
    other = other - float(other @ a) * a  # keep only the part that is not like `a`
    other = other / np.linalg.norm(other)
    v = likeness * a + float(np.sqrt(1.0 - likeness ** 2)) * other
    return v.astype(np.float32)


ALICE, BOB = unit(10), unit(20)


class FakeEar:
    """The 'recording' is a name, a name is a voice, and @5 means five seconds of speech."""

    voices = {
        b"alice": ALICE,
        b"bob": BOB,
        b"carol": unit(30),                       # nobody she knows
        b"alicecold": like(ALICE, 0.40, 8),         # 0.4 like Alice: not sure
    }

    def tools_missing(self):
        return ""

    def models_ready(self):
        return True

    def analyze(self, data, min_speech=V.VERIFY_SPEECH):
        name, _, secs = data.partition(b"@")
        seconds = float(secs or 5)
        info = {"seconds": seconds, "speech": seconds, "peak_db": -20.0, "floor_db": -60.0, "problem": ""}
        if name not in self.voices:
            info.update(speech=0.0, problem="I can hardly hear you. Speak a little louder, or move closer to the microphone.")
            return info, None
        if seconds < min_speech:
            info["problem"] = f"I heard only {seconds:.1f} seconds of your voice and I need {min_speech:.0f}."
            return info, None
        return info, self.voices[name]

    def one_voice(self, data, min_speech=V.ENROLL_SPEECH):
        info, vector = self.analyze(data, min_speech)
        if vector is None:
            raise V.VoiceError(info["problem"])
        return info, vector


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(routes, "voice_engine", lambda: FakeEar())
    app = FastAPI()

    def authorize(header):
        if header != "Bearer ok":
            raise HTTPException(status_code=401, detail="no")

    routes.register_identity_routes(app, authorize, FakeDB)
    c = TestClient(app)
    c.headers.update({"Authorization": "Bearer ok"})
    return c


def audio(name: bytes) -> str:
    return "data:audio/wav;base64," + base64.b64encode(name).decode()


def teach(client, name, who, times=3):
    for _ in range(times):
        assert client.post("/v1/identity/voice/enroll", json={"name": name, "audio": audio(who + b"@6")}).status_code == 200


def verify(client, clip):
    return client.post("/v1/identity/voice/verify", json={"audio": audio(clip)}).json()


# ---------- the word itself ----------
def result_for(vector, samples):
    return ids.decide_voice(vector, samples, {"a": "Alice", "b": "Bob"})


def test_a_clear_match_is_a_match():
    out = result_for(like(ALICE, 0.95, 3), [("a", ALICE), ("b", BOB)])
    assert ids.classify_voice(out, 5.0) == "match" and out["match"]["name"] == "Alice"


def test_a_voice_like_nobody_she_knows_is_other_when_there_was_enough_speech():
    out = result_for(unit(99), [("a", ALICE), ("b", BOB)])
    assert out["match"] is None and out["closest"]["score"] < ids.VOICE_OTHER
    assert ids.classify_voice(out, ids.OTHER_SPEECH) == "other"


def test_a_clip_with_too_little_speech_never_says_other():
    out = result_for(unit(99), [("a", ALICE), ("b", BOB)])
    assert ids.classify_voice(out, ids.OTHER_SPEECH - 0.1) == "unsure"
    assert ids.classify_voice(out, 0.0) == "unsure"
    assert ids.classify_voice(out, 1.0, min_speech=1.0) == "other"   # a caller can ask for less or more


def test_something_in_between_is_only_not_sure():
    out = result_for(like(ALICE, 0.40, 8), [("a", ALICE), ("b", BOB)])
    assert out["match"] is None and ids.VOICE_OTHER < out["closest"]["score"] < ids.VOICE_THRESHOLD
    assert ids.classify_voice(out, 8.0) == "unsure"


def test_no_voice_taught_yet_is_nobody():
    assert ids.classify_voice(ids.decide_voice(ALICE, [], {}), 8.0) == "nobody"


def test_the_lines_are_ordered_so_that_other_sits_under_a_match():
    assert 0.0 < ids.VOICE_OTHER < ids.VOICE_THRESHOLD < 1.0 and ids.OTHER_SPEECH >= V.VERIFY_SPEECH


def test_the_other_line_can_be_moved_by_the_caller():
    out = result_for(like(ALICE, 0.40, 8), [("a", ALICE), ("b", BOB)])
    assert ids.classify_voice(out, 8.0, other=0.90) == "other"


# ---------- the endpoint ----------
def test_the_answer_says_match_for_a_known_voice(client):
    teach(client, "Alice", b"alice")
    teach(client, "Bob", b"bob")
    got = verify(client, b"alice@5")
    assert got["verdict"] == "match" and got["match"]["name"] == "Alice" and got["heard"] is True
    assert verify(client, b"bob@4")["verdict"] == "match"


def test_the_answer_says_other_for_a_stranger_with_enough_speech(client):
    teach(client, "Alice", b"alice")
    got = verify(client, b"carol@5")
    assert got["verdict"] == "other" and got["match"] is None and got["heard"] is True


def test_a_stranger_with_too_little_speech_is_not_judged_at_all(client):
    teach(client, "Alice", b"alice")
    got = verify(client, b"carol@1.5")
    assert got["verdict"] == "unheard" and got["heard"] is False and got["match"] is None
    short = verify(client, b"carol@2")   # the least the engine accepts is enough to say "nobody I know"
    assert short["verdict"] == "other" and short["heard"] is True


def test_a_weak_likeness_is_not_sure(client):
    teach(client, "Alice", b"alice")
    got = verify(client, b"alicecold@6")
    assert got["verdict"] == "unsure" and got["match"] is None


def test_too_little_sound_is_unheard(client):
    teach(client, "Alice", b"alice")
    short = verify(client, b"alice@1")
    assert short["verdict"] == "unheard" and short["heard"] is False
    silent = verify(client, b"nobody")
    assert silent["verdict"] == "unheard" and silent["heard"] is False


def test_with_no_voice_taught_the_answer_says_nobody(client):
    got = verify(client, b"alice@5")
    assert got["verdict"] == "nobody" and got["closest"] is None and "do not know your voice" in got["message"]


def test_the_old_answer_is_all_still_there(client):
    teach(client, "Alice", b"alice")
    got = verify(client, b"alice@5")
    assert {"heard", "match", "closest", "speech", "seconds", "message"} <= set(got)
    assert got["match"]["name"] == "Alice" and set(got["match"]) == {"person_id", "name", "score"}
    unheard = verify(client, b"alice@1")
    assert {"heard", "match", "closest", "speech", "seconds", "message"} <= set(unheard)


def test_the_status_answer_is_unchanged(client):
    assert client.get("/v1/identity/status").json()["voice"] == {"available": True, "reason": "", "models_ready": True, "threshold": ids.VOICE_THRESHOLD}


def test_the_token_is_still_required(client):
    wrong = {"Authorization": "Bearer wrong"}
    assert client.post("/v1/identity/voice/verify", json={"audio": audio(b"alice@5")}, headers=wrong).status_code == 401
