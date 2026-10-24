"""Voice ID: everything that needs no model (WAV reading, finding speech, features,
matching, storage, endpoints). One last test runs the real model, but only when it is
already on this computer. A test never downloads anything.
"""
import base64
import hashlib
import io
import sqlite3
import wave

import numpy as np
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from iras.identity import routes, store as ids, voice as V
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


# ---------- made-up sound ----------
def wav(samples, rate=16000, channels=1, width=2) -> bytes:
    x = np.clip(np.asarray(samples, np.float32), -1.0, 1.0)
    if channels > 1:
        x = np.repeat(x[:, None], channels, axis=1).reshape(-1)  # the same sound in every channel
    if width == 2:
        raw = (x * 32767).astype("<i2").tobytes()
    elif width == 1:
        raw = (x * 127 + 128).astype(np.uint8).tobytes()
    elif width == 3:
        raw = (x * 8388607).astype("<i4").view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    else:
        raw = (x * 2147483647).astype("<i4").tobytes()
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(raw)
    return out.getvalue()


def voiced(seconds, pitch=120.0, rate=16000, level=0.2):
    """A buzzy, speech-like sound: a pitch with harmonics, getting louder and softer like syllables."""
    t = np.arange(int(seconds * rate)) / rate
    x = sum(np.sin(2 * np.pi * pitch * k * t) / k for k in range(1, 12)) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
    return (level * x / np.max(np.abs(x))).astype(np.float32)


def talk(bursts=3, burst=0.8, gap=0.6, pitch=120.0):
    """Short bursts of speech with quiet pauses between them."""
    rng = np.random.default_rng(0)
    parts = []
    for _ in range(bursts):
        parts += [voiced(burst, pitch), rng.normal(scale=0.0003, size=int(gap * V.RATE)).astype(np.float32)]
    return np.concatenate(parts)


# ---------- reading a recording ----------
def test_a_16_bit_wav_is_read_back_as_it_was_sent():
    x = voiced(1.0)
    y = V.decode_wav(wav(x))
    assert y.dtype == np.float32 and len(y) == len(x) and np.abs(y - x).max() < 1e-3


@pytest.mark.parametrize("width,tolerance", [(1, 0.02), (3, 1e-4), (4, 1e-4)])
def test_other_bit_depths_are_read_too(width, tolerance):
    x = voiced(0.5)
    y = V.decode_wav(wav(x, width=width))
    assert len(y) == len(x) and np.abs(y - x).max() < tolerance


def test_stereo_and_other_rates_become_mono_16k():
    x = voiced(1.0, rate=48000)
    y = V.decode_wav(wav(x, rate=48000, channels=2))
    assert abs(len(y) - 16000) <= 1
    assert abs(float(np.sqrt((y ** 2).mean())) - float(np.sqrt((x ** 2).mean()))) < 0.02


def test_resampling_keeps_a_tone_and_drops_what_cannot_fit():
    rate = 48000
    t = np.arange(rate) / rate
    kept = V.resample(np.sin(2 * np.pi * 440 * t).astype(np.float32), rate)
    dropped = V.resample(np.sin(2 * np.pi * 20000 * t).astype(np.float32), rate)  # 20 kHz cannot exist at 16 kHz
    assert len(kept) == 16000
    assert abs(int(np.argmax(np.abs(np.fft.rfft(kept)))) - 440) <= 1
    assert float(np.sqrt((dropped ** 2).mean())) < 0.02  # filtered away, not folded down into the voice
    assert len(V.resample(np.zeros(8000, np.float32), 8000)) == 16000  # going up works too


def test_bad_recordings_are_refused_in_plain_words():
    for bad in (b"", b"this is not a wav file", wav(voiced(0.5))[:30]):
        with pytest.raises(V.VoiceError):
            V.decode_wav(bad)
    with pytest.raises(V.VoiceError, match="too long"):
        V.decode_wav(wav(np.zeros(16000 * (V.MAX_AUDIO_SECONDS + 1), np.float32)))
    with pytest.raises(V.VoiceError, match="too large"):
        V.decode_wav(b"RIFF" + b"0" * (V.MAX_AUDIO_BYTES + 1))
    with pytest.raises(V.VoiceError):
        V.decode_wav(wav(voiced(0.5), rate=1000))  # not a rate any microphone makes


# ---------- finding the speech ----------
def test_silence_and_a_quiet_room_are_not_speech():
    speech, info = V.trim_speech(np.zeros(V.RATE * 3, np.float32))
    assert len(speech) == 0 and "hardly hear" in info["problem"]
    hiss = np.random.default_rng(2).normal(scale=0.0003, size=V.RATE * 3).astype(np.float32)
    assert "hardly hear" in V.trim_speech(hiss)[1]["problem"]


def test_speech_is_kept_and_the_pauses_are_cut():
    x = talk(bursts=3, burst=0.8, gap=0.6)
    speech, info = V.trim_speech(x)
    assert info["problem"] == ""
    assert 2.2 <= info["speech"] <= 3.0  # three bursts of 0.8 s, plus a little around each
    assert len(speech) < len(x) and info["seconds"] == pytest.approx(len(x) / V.RATE, abs=0.01)


def test_sound_that_never_stops_is_called_too_noisy():
    noise = np.random.default_rng(1).normal(scale=0.05, size=V.RATE * 4).astype(np.float32)
    assert "too noisy" in V.trim_speech(noise)[1]["problem"]


def test_a_fragment_is_too_short_to_judge():
    assert "too short" in V.trim_speech(np.zeros(1000, np.float32))[1]["problem"]


def test_a_long_talk_is_cut_to_the_limit():
    speech, info = V.trim_speech(voiced(V.MAX_SPEECH_SECONDS + 8))
    assert info["speech"] == pytest.approx(V.MAX_SPEECH_SECONDS, abs=0.01) and len(speech) == int(V.MAX_SPEECH_SECONDS * V.RATE)


# ---------- the features the model reads ----------
def test_features_have_the_shape_the_model_expects():
    f = V.fbank(voiced(1.0))
    assert f.shape == (98, 80) and f.dtype == np.float32  # 1 + (16000 - 400) // 160 frames, 80 bands
    assert np.isfinite(f).all() and np.abs(f.mean(axis=0)).max() < 1e-4


def test_features_do_not_care_how_loud_you_are():
    x = voiced(1.0)
    assert np.abs(V.fbank(x) - V.fbank(0.25 * x)).max() < 1e-3


def test_features_see_the_pitch_of_a_voice():
    assert np.abs(V.fbank(voiced(1.0, 120.0)) - V.fbank(voiced(1.0, 200.0))).mean() > 0.1


def test_features_need_enough_sound():
    with pytest.raises(V.VoiceError):
        V.fbank(np.zeros(V.FRAME - 1, np.float32))


def test_features_match_the_kaldi_reference():
    knf = pytest.importorskip("kaldi_native_fbank")
    x = voiced(1.5) + np.random.default_rng(3).normal(scale=0.002, size=24000).astype(np.float32)
    o = knf.FbankOptions()
    o.frame_opts.dither = 0.0
    o.frame_opts.samp_freq = 16000
    o.frame_opts.window_type = "hamming"
    o.frame_opts.snip_edges = True
    o.mel_opts.num_bins = 80
    o.mel_opts.low_freq = 20
    o.mel_opts.high_freq = 0
    f = knf.OnlineFbank(o)
    f.accept_waveform(16000, (x * 32768).tolist())
    f.input_finished()
    ref = np.stack([f.get_frame(i) for i in range(f.num_frames_ready)])
    ref -= ref.mean(axis=0, keepdims=True)
    mine = V.fbank(x)
    assert mine.shape == ref.shape and np.abs(mine - ref).max() < 5e-3


# ---------- deciding who it is ----------
def unit(seed, size=256):
    v = np.random.default_rng(seed).normal(size=size).astype(np.float32)
    return v / np.linalg.norm(v)


def near(vec, noise, seed):
    v = vec + np.random.default_rng(seed).normal(scale=noise, size=len(vec)).astype(np.float32)
    return v / np.linalg.norm(v)


def test_a_voice_is_compared_with_each_persons_average():
    alice, bob = unit(1), unit(2)
    samples = [("a", near(alice, 0.02, 3)), ("a", near(alice, 0.02, 4)), ("b", bob)]
    names = {"a": "Alice", "b": "Bob"}
    hit = ids.decide_voice(near(alice, 0.02, 5), samples, names)
    assert hit["match"]["name"] == "Alice" and hit["match"]["score"] > 0.8
    stranger = ids.decide_voice(unit(99), samples, names)
    assert stranger["match"] is None and stranger["closest"] is not None
    assert ids.decide_voice(alice, [], {}) == {"match": None, "closest": None}


def test_two_voices_that_sound_alike_are_not_guessed():
    base = unit(5)
    out = ids.decide_voice(base, [("a", near(base, 0.01, 6)), ("b", near(base, 0.01, 7))], {"a": "A", "b": "B"})
    assert out["match"] is None  # too close to call, so she asks instead of guessing


def test_a_weak_likeness_is_not_a_match():
    alice = unit(1)
    weak = alice * 0.4 + unit(8) * 0.9  # about 0.4 like Alice
    weak = weak / np.linalg.norm(weak)
    out = ids.decide_voice(weak, [("a", alice)], {"a": "Alice"})
    assert 0.2 < out["closest"]["score"] < ids.VOICE_THRESHOLD and out["match"] is None


# ---------- keeping voiceprints ----------
def test_voiceprints_are_kept_up_to_a_limit_and_can_be_forgotten_alone():
    s = ids.IdentityStore(FakeDB())
    p = s.add_person("Hamza")
    for i in range(ids.MAX_VOICE_SAMPLES + 3):
        count = s.add_voice(p["person_id"], unit(i))
    assert count == ids.MAX_VOICE_SAMPLES
    assert s.people()[0]["voices"] == ids.MAX_VOICE_SAMPLES and len(s.voice_samples()) == ids.MAX_VOICE_SAMPLES
    assert len(s.voices_of(p["person_id"])) == ids.MAX_VOICE_SAMPLES
    s.add_face(p["person_id"], unit(0, 512))
    s.forget_voice(p["person_id"])
    left = s.people()[0]
    assert left["voices"] == 0 and left["faces"] == 1  # the face is still known, so the person stays
    s.forget_face(p["person_id"])
    assert s.people() == []  # nothing left to remember, so the name goes too


def test_forgetting_a_person_forgets_the_voice_as_well():
    s = ids.IdentityStore(FakeDB())
    p = s.add_person("Sam")
    s.add_voice(p["person_id"], unit(1))
    s.add_face(p["person_id"], unit(2, 512))
    s.delete_person(p["person_id"])
    assert s.people() == [] and s.voice_samples() == [] and s.samples() == []


# ---------- the endpoints ----------
class FakeEar:
    """Stands in for the model: the 'recording' is a name, a name is a voice, and @5 means five seconds."""

    voices = {b"alice": unit(10), b"bob": unit(20), b"carol": unit(30)}

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
            info["problem"] = f"I heard only {seconds:.1f} seconds of your voice and I need {min_speech:.0f}. Keep talking until the bar ends."
            return info, None
        return info, self.voices[name]

    def one_voice(self, data, min_speech=V.ENROLL_SPEECH):
        info, vector = self.analyze(data, min_speech)
        if vector is None:
            raise V.VoiceError(info["problem"])
        return info, vector


class FakeEye:
    """The same idea for faces: the 'picture' is a name."""

    def tools_missing(self):
        return ""

    def models_ready(self):
        return True

    def one_face(self, data):
        return Face((0, 0, 100, 100), 0.9, [[30, 40], [70, 40], [50, 60], [35, 80], [65, 80]]), unit(40, 512)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(routes, "voice_engine", lambda: FakeEar())
    monkeypatch.setattr(routes, "engine", lambda: FakeEye())
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


def test_voice_endpoints_need_the_token(client):
    wrong = {"Authorization": "Bearer wrong"}
    assert client.post("/v1/identity/voice/verify", json={"audio": audio(b"alice")}, headers=wrong).status_code == 401
    assert client.post("/v1/identity/voice/enroll", json={"name": "A", "audio": audio(b"alice")}, headers=wrong).status_code == 401
    assert client.delete("/v1/identity/people/x/voice", headers=wrong).status_code == 401
    assert client.delete("/v1/identity/people/x/face", headers=wrong).status_code == 401


def test_status_tells_about_voice_too(client):
    status = client.get("/v1/identity/status").json()
    assert status["available"] is True  # the face part is unchanged
    assert status["voice"] == {"available": True, "reason": "", "models_ready": True, "threshold": ids.VOICE_THRESHOLD}


def test_teach_then_recognise_then_forget_a_voice(client):
    for _ in range(3):
        r = client.post("/v1/identity/voice/enroll", json={"name": "Alice", "audio": audio(b"alice@6")})
        assert r.status_code == 200
    assert r.json()["samples"] == 3 and r.json()["quality"]["speech"] == 6.0
    assert client.post("/v1/identity/voice/enroll", json={"name": "Bob", "audio": audio(b"bob@6")}).status_code == 200
    people = client.get("/v1/identity/people").json()["people"]
    assert sorted((p["name"], p["voices"], p["faces"]) for p in people) == [("Alice", 3, 0), ("Bob", 1, 0)]

    who = client.post("/v1/identity/voice/verify", json={"audio": audio(b"alice@5")}).json()
    assert who["heard"] is True and who["match"]["name"] == "Alice" and who["message"] == ""

    stranger = client.post("/v1/identity/voice/verify", json={"audio": audio(b"carol@5")}).json()
    assert stranger["heard"] is True and stranger["match"] is None and "not sure" in stranger["message"]

    short = client.post("/v1/identity/voice/verify", json={"audio": audio(b"alice@1")}).json()
    assert short["heard"] is False and short["match"] is None and "heard only" in short["message"]

    silent = client.post("/v1/identity/voice/verify", json={"audio": audio(b"nobody")}).json()
    assert silent["heard"] is False and "hardly hear" in silent["message"]

    alice_id = next(p["person_id"] for p in people if p["name"] == "Alice")
    assert client.delete(f"/v1/identity/people/{alice_id}/voice").status_code == 200
    gone = client.post("/v1/identity/voice/verify", json={"audio": audio(b"alice@5")}).json()
    assert gone["match"] is None
    assert [p["name"] for p in client.get("/v1/identity/people").json()["people"]] == ["Bob"]


def test_nobody_is_known_yet(client):
    out = client.post("/v1/identity/voice/verify", json={"audio": audio(b"alice@5")}).json()
    assert out["heard"] is True and out["match"] is None and out["closest"] is None and "do not know your voice" in out["message"]


def test_teaching_errors_are_plain(client):
    r = client.post("/v1/identity/voice/enroll", json={"audio": audio(b"alice@6")})
    assert r.status_code == 422 and "who this is" in r.json()["detail"]
    r = client.post("/v1/identity/voice/enroll", json={"name": "X", "audio": audio(b"alice@2")})
    assert r.status_code == 422 and "heard only" in r.json()["detail"]
    r = client.post("/v1/identity/voice/enroll", json={"name": "X", "audio": audio(b"nobody")})
    assert r.status_code == 422 and "hardly hear" in r.json()["detail"]
    assert client.post("/v1/identity/voice/enroll", json={"name": "X"}).status_code == 422  # no recording at all


def test_someone_else_cannot_join_a_voice_that_is_already_known(client):
    for _ in range(2):
        assert client.post("/v1/identity/voice/enroll", json={"name": "Alice", "audio": audio(b"alice@6")}).status_code == 200
    r = client.post("/v1/identity/voice/enroll", json={"name": "Alice", "audio": audio(b"bob@6")})
    assert r.status_code == 422 and "does not sound like" in r.json()["detail"]
    assert client.get("/v1/identity/people").json()["people"][0]["voices"] == 2  # nothing was added


def test_a_server_without_the_tools_says_so(client, monkeypatch):
    class Broken(FakeEar):
        def tools_missing(self):
            return "Voice ID needs numpy and onnxruntime on the server (onnxruntime is missing)."

        def analyze(self, data, min_speech=V.VERIFY_SPEECH):
            raise V.VoiceUnavailable(self.tools_missing())

    monkeypatch.setattr(routes, "voice_engine", lambda: Broken())
    r = client.post("/v1/identity/voice/verify", json={"audio": audio(b"alice@5")})
    assert r.status_code == 503 and "onnxruntime" in r.json()["detail"]
    status = client.get("/v1/identity/status").json()
    assert status["voice"]["available"] is False and "onnxruntime" in status["voice"]["reason"]


def test_face_and_voice_can_be_forgotten_one_at_a_time(client):
    assert client.post("/v1/identity/voice/enroll", json={"name": "Alice", "audio": audio(b"alice@6")}).status_code == 200
    assert client.post("/v1/identity/face/enroll", json={"name": "Alice", "image": "aGk="}).status_code == 200
    person = client.get("/v1/identity/people").json()["people"][0]
    assert person["voices"] == 1 and person["faces"] == 1
    client.delete(f"/v1/identity/people/{person['person_id']}/face")
    person = client.get("/v1/identity/people").json()["people"][0]
    assert person["voices"] == 1 and person["faces"] == 0
    client.delete(f"/v1/identity/people/{person['person_id']}/voice")
    assert client.get("/v1/identity/people").json()["people"] == []


def test_the_whole_person_can_still_be_forgotten_at_once(client):
    client.post("/v1/identity/voice/enroll", json={"name": "Alice", "audio": audio(b"alice@6")})
    client.post("/v1/identity/face/enroll", json={"name": "Alice", "image": "aGk="})
    person_id = client.get("/v1/identity/people").json()["people"][0]["person_id"]
    assert client.delete(f"/v1/identity/people/{person_id}").status_code == 200
    assert client.get("/v1/identity/people").json()["people"] == []


# ---------- downloading the model (no network: the download is faked) ----------
class FakeDownload:
    def __init__(self, data: bytes):
        self.stream = io.BytesIO(data)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        return self.stream.read(n)


def test_the_model_download_is_checked(tmp_path, monkeypatch):
    good = b"m" * (V.MODEL_MIN_BYTES + 10)
    monkeypatch.setattr(V.urllib.request, "urlopen", lambda *a, **k: FakeDownload(good))
    monkeypatch.setattr(V, "MODEL_SHA256", hashlib.sha256(good).hexdigest())
    ear = V.VoiceEngine(model_dir=tmp_path)
    ear._download()
    assert ear.models_ready() and ear.path.read_bytes() == good and not list(tmp_path.glob("*.part"))

    other = V.VoiceEngine(model_dir=tmp_path / "wrong")
    monkeypatch.setattr(V.urllib.request, "urlopen", lambda *a, **k: FakeDownload(b"x" * (V.MODEL_MIN_BYTES + 10)))
    with pytest.raises(V.VoiceUnavailable, match="checksum"):
        other._download()
    assert not other.models_ready() and not list((tmp_path / "wrong").glob("*.part"))  # a bad file is never kept

    monkeypatch.setattr(V.urllib.request, "urlopen", lambda *a, **k: FakeDownload(b"tiny"))
    with pytest.raises(V.VoiceUnavailable, match="too small"):
        other._download()

    def offline(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(V.urllib.request, "urlopen", offline)
    with pytest.raises(V.VoiceUnavailable, match="Could not download"):
        other._download()


# ---------- the real model ----------
def test_the_real_model_if_it_is_already_here(monkeypatch):
    pytest.importorskip("onnxruntime")
    monkeypatch.delenv("IRAS_VOICE_KEEP_LOADED", raising=False)
    ear = V.VoiceEngine()
    if not ear.models_ready():
        pytest.skip("the voice model is not on this computer (tests never download it)")
    data = wav(talk())
    info, a = ear.analyze(data, 1.0)
    assert info["problem"] == "" and a.shape == (256,) and abs(float(np.linalg.norm(a)) - 1.0) < 1e-4
    _, b = ear.analyze(data, 1.0)
    assert float(a @ b) > 0.999  # the same sound gives the same voiceprint
    assert ear._session is None  # the model is let go after each check, to save memory
