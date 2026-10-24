"""Voice ID: one small ONNX model, no recording is ever kept.

  WeSpeaker ResNet34   turns a few seconds of speech into 256 numbers (a "voiceprint")

It is the English VoxCeleb ResNet34 model from the WeSpeaker project, packed for ONNX
by the sherpa-onnx project. It is downloaded on first use (26 MB) from GitHub, and
its checksum is checked. WeSpeaker's code is Apache 2.0. Its VoxCeleb models follow
the CC BY 4.0 licence of that dataset, so give credit to WeSpeaker if you share
this. Needs: numpy and onnxruntime (the "identity" extra installs both).

The browser sends a short WAV: 16 kHz, 16 bit, one channel is best. Other rates
and stereo are fixed here. Everything before the model is plain numpy:

  decode_wav     WAV bytes -> mono float samples at 16 kHz
  trim_speech    keep the loud parts (speech) and measure the recording
  fbank          the same 80-band log-mel features the model was trained on

A voice can be recorded and played back, so Voice ID is a hint about who is
talking (for greetings and personal answers). It never unlocks an approval.
"""
from __future__ import annotations

import hashlib
import io
import os
import tempfile
import threading
import urllib.request
import wave
from pathlib import Path
from urllib.parse import unquote, urlparse

DEFAULT_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/wespeaker_en_voxceleb_resnet34.onnx"
)
DEFAULT_MODEL_SHA256 = "5ef208a9da1453335308a6b6f4e6dfbd7e183a38b604de0a57664f45d257fe94"
MODEL_URL = os.getenv("IRAS_VOICE_MODEL_URL", DEFAULT_MODEL_URL)
# The checksum is pinned for the default model. For your own model, set IRAS_VOICE_MODEL_SHA256
# to its checksum, or to "off" to skip the check.
_SHA = os.getenv("IRAS_VOICE_MODEL_SHA256", DEFAULT_MODEL_SHA256 if MODEL_URL == DEFAULT_MODEL_URL else "").strip().lower()
MODEL_SHA256 = "" if _SHA in ("off", "none", "skip") else _SHA
MODEL_FILE = unquote(Path(urlparse(MODEL_URL).path).name) or "voice-model.onnx"
MODEL_MIN_BYTES = 5 * 1024 * 1024

RATE = 16000
MAX_AUDIO_BYTES = 8 * 1024 * 1024  # one recording, as sent
MAX_AUDIO_SECONDS = 60
MAX_SPEECH_SECONDS = 10.0  # more speech than this is cut: the voiceprint does not need it, and memory is small
ENROLL_SPEECH = 3.0  # seconds of real speech needed to teach her a voice
VERIFY_SPEECH = 2.0  # seconds of real speech needed to ask "who is this?"
FRAME = 400  # 25 ms
HOP = 160  # 10 ms
FFT = 512
BINS = 80
_FLOOR = 1.1920929e-07  # float32 epsilon, the smallest value a mel band is allowed to have


class VoiceUnavailable(RuntimeError):
    """Voice ID cannot run here (tools or model missing). The message says why."""


class VoiceError(ValueError):
    """The recording cannot be used (too short, too quiet, not a WAV). Safe to show the user."""


# ---------- recordings ----------
def resample(samples, source_rate: int, target_rate: int = RATE):
    """Change the sample rate. Going down, a low-pass filter first, so high sounds do not fold into the voice."""
    import numpy as np

    x = np.asarray(samples, np.float32)
    if source_rate == target_rate or len(x) == 0:
        return x
    if source_rate > target_rate:
        cutoff = 0.45 * target_rate / source_rate  # as a fraction of the source rate
        taps = np.arange(-50, 51)
        kernel = np.sinc(2 * cutoff * taps) * np.hamming(len(taps))
        kernel /= kernel.sum()
        x = np.convolve(x, kernel, mode="same").astype(np.float32)
    count = max(1, int(round(len(x) * target_rate / source_rate)))
    positions = np.arange(count) * (source_rate / target_rate)
    return np.interp(positions, np.arange(len(x)), x).astype(np.float32)


def decode_wav(data: bytes):
    """A PCM WAV (8, 16, 24 or 32 bit; any channels or rate) -> mono float32 samples at 16 kHz in [-1, 1]."""
    import numpy as np

    if not data or len(data) > MAX_AUDIO_BYTES:
        raise VoiceError("The recording is empty or too large.")
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            channels, width, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            if not 8000 <= rate <= 96000 or channels < 1:
                raise VoiceError("I could not read that recording.")
            if frames > rate * MAX_AUDIO_SECONDS:
                raise VoiceError(f"The recording is too long. Keep it under {MAX_AUDIO_SECONDS} seconds.")
            raw = w.readframes(frames)
    except VoiceError:
        raise
    except Exception as exc:  # a broken header, a format the wave module does not know
        raise VoiceError("I could not read that recording. It must be a plain WAV file.") from exc
    if width == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    elif width == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = (((v ^ 0x800000) - 0x800000).astype(np.float32)) / 8388608.0
    elif width == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648.0
    else:
        raise VoiceError("I could not read that recording.")
    if channels > 1:
        x = x[: len(x) // channels * channels].reshape(-1, channels).mean(axis=1)
    return resample(x, rate)


def trim_speech(samples):
    """Keep only the loud parts (speech) of a recording. Returns (speech samples, info).

    info: seconds (whole recording), speech (kept), peak_db and floor_db (loud and quiet levels,
    in dB below full scale), problem ("" or a plain sentence that says what to change).
    """
    import numpy as np

    x = np.asarray(samples, np.float32)
    step = RATE // 50  # 20 ms
    count = len(x) // step
    info = {"seconds": round(len(x) / RATE, 2), "speech": 0.0, "peak_db": -120.0, "floor_db": -120.0, "problem": ""}
    if count < 10:
        info["problem"] = "That was too short. Speak for a few seconds."
        return x[:0], info
    frames = x[: count * step].reshape(count, step)
    db = 20.0 * np.log10(np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1)) + 1e-9)
    peak, floor = float(np.percentile(db, 95)), float(np.percentile(db, 10))
    info["peak_db"], info["floor_db"] = round(peak, 1), round(floor, 1)
    if peak < -50.0:
        info["problem"] = "I can hardly hear you. Speak a little louder, or move closer to the microphone."
        return x[:0], info
    voiced = db > max(peak - 32.0, floor + 6.0, -58.0)
    voiced = np.convolve(voiced.astype(np.float32), np.ones(5, np.float32), mode="same") > 0  # keep soft sounds next to loud ones
    speech = frames[voiced].reshape(-1)[: int(MAX_SPEECH_SECONDS * RATE)]
    info["speech"] = round(len(speech) / RATE, 2)
    if peak - floor < 8.0:
        info["problem"] = "It is too noisy here, or the sound never stops. Find a quiet place and speak with pauses."
    return speech, info


# ---------- features ----------
_CACHE: dict = {}


def _tables():
    """The Hamming window and the 80 mel bands, built the way Kaldi builds them (the model was trained on these)."""
    import numpy as np

    if not _CACHE:
        n = np.arange(FRAME)
        _CACHE["window"] = 0.54 - 0.46 * np.cos(2.0 * np.pi * n / (FRAME - 1))
        mel = lambda f: 1127.0 * np.log(1.0 + f / 700.0)  # noqa: E731
        low, high = 20.0, RATE / 2.0
        step = (mel(high) - mel(low)) / (BINS + 1)
        freqs = (RATE / FFT) * np.arange(FFT // 2)  # the top bin (8000 Hz) is left out, as in Kaldi
        mels = mel(freqs)
        bank = np.zeros((FFT // 2 + 1, BINS))
        for b in range(BINS):
            left = mel(low) + b * step
            centre, right = left + step, left + 2 * step
            bank[: FFT // 2, b] = np.maximum(0.0, np.minimum((mels - left) / (centre - left), (right - mels) / (right - centre)))
        _CACHE["bank"] = bank
    return _CACHE["window"], _CACHE["bank"]


def fbank(samples):
    """80 log-mel numbers for every 10 ms (25 ms windows), with each band's average removed. Shape (frames, 80).

    Samples are floats in [-1, 1]. The model was trained on whole-number sample values, so they are scaled by 32768.
    """
    import numpy as np

    x = np.asarray(samples, np.float64) * 32768.0
    if len(x) < FRAME:
        raise VoiceError("That was too short. Speak for a few seconds.")
    window, bank = _tables()
    frames = np.lib.stride_tricks.sliding_window_view(x, FRAME)[::HOP].copy()
    frames -= frames.mean(axis=1, keepdims=True)  # remove the DC offset
    emphasized = np.empty_like(frames)  # pre-emphasis: lift the high sounds a little
    emphasized[:, 1:] = frames[:, 1:] - 0.97 * frames[:, :-1]
    emphasized[:, 0] = frames[:, 0] * (1.0 - 0.97)
    spectrum = np.fft.rfft(emphasized * window, n=FFT, axis=1)
    power = spectrum.real ** 2 + spectrum.imag ** 2
    feats = np.log(np.maximum(power @ bank, _FLOOR))
    return (feats - feats.mean(axis=0, keepdims=True)).astype(np.float32)


# ---------- the model ----------
class VoiceEngine:
    def __init__(self, model_dir: str | os.PathLike | None = None) -> None:
        base = model_dir or os.getenv("IRAS_VOICE_MODEL_DIR") or Path(tempfile.gettempdir()) / "iras-voice-models"
        self.dir = Path(base)
        self._lock = threading.Lock()
        self._session = None
        self._input = ""
        # A small server (512 MB) cannot hold the model all day next to everything else.
        # By default it is loaded for each check and let go afterwards (about 0.3 seconds).
        self.keep_loaded = os.getenv("IRAS_VOICE_KEEP_LOADED", "").strip().lower() in ("1", "true", "yes", "on")

    # ---------- setup ----------
    @staticmethod
    def tools_missing() -> str:
        try:
            import numpy  # noqa: F401
            import onnxruntime  # noqa: F401
        except ImportError as exc:
            return f"Voice ID needs numpy and onnxruntime on the server ({exc.name} is missing)."
        return ""

    @property
    def path(self) -> Path:
        return self.dir / MODEL_FILE

    def models_ready(self) -> bool:
        return self.path.exists()

    def _download(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".part")
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(MODEL_URL, timeout=90) as response, open(temp, "wb") as out:
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    digest.update(chunk)
                    out.write(chunk)
            if temp.stat().st_size < MODEL_MIN_BYTES:
                raise VoiceUnavailable("The voice model download is too small to be the model.")
            if MODEL_SHA256 and digest.hexdigest() != MODEL_SHA256:
                raise VoiceUnavailable(
                    "The voice model failed its checksum, so I did not use it. "
                    "If you changed IRAS_VOICE_MODEL_URL, set IRAS_VOICE_MODEL_SHA256 to match (or to off)."
                )
            temp.replace(self.path)
        except VoiceUnavailable:
            temp.unlink(missing_ok=True)
            raise
        except Exception as exc:  # network, disk
            temp.unlink(missing_ok=True)
            raise VoiceUnavailable(f"Could not download the voice model ({type(exc).__name__}: {exc}).") from exc

    def _load(self) -> None:
        """Make sure the model file is here and can be opened. Call it with the lock held."""
        missing = self.tools_missing()
        if missing:
            raise VoiceUnavailable(missing)
        if self._session is not None:
            return
        import onnxruntime as ort

        if not self.models_ready():
            self._download()
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, int(os.getenv("IRAS_VOICE_THREADS", "1") or 1))
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        session = ort.InferenceSession(str(self.path), options, providers=["CPUExecutionProvider"])
        shape = session.get_inputs()[0].shape
        if len(shape) != 3 or shape[-1] != BINS or len(session.get_outputs()) < 1:
            raise VoiceUnavailable("The voice model is not the expected one (it must take 80-band features).")
        self._input = session.get_inputs()[0].name
        self._session = session

    # ---------- the voiceprint ----------
    def embed(self, speech):
        """Samples (16 kHz, floats) -> a voiceprint: the model's numbers, scaled to length 1."""
        import numpy as np

        feats = fbank(speech)[None, :, :]
        with self._lock:  # one voice at a time: a small server has no room for two runs together
            try:
                self._load()
                vector = np.asarray(self._session.run(None, {self._input: feats})[0][0], np.float32).reshape(-1)
            finally:
                if not self.keep_loaded:
                    self._session = None  # frees the model's memory
        return vector / (float(np.linalg.norm(vector)) + 1e-9)

    def analyze(self, data: bytes, min_speech: float = VERIFY_SPEECH):
        """Look at a recording. Returns (info, voiceprint). The voiceprint is None when there is too little speech."""
        speech, info = trim_speech(decode_wav(data))
        if info["problem"] or info["speech"] < min_speech:
            if not info["problem"]:
                info["problem"] = (
                    f"I heard only {info['speech']:.1f} seconds of your voice and I need {min_speech:.0f}. "
                    "Keep talking until the bar ends."
                )
            return info, None
        return info, self.embed(speech)

    def one_voice(self, data: bytes, min_speech: float = ENROLL_SPEECH):
        """A recording that must hold enough clear speech. Returns (info, voiceprint), or says what to fix."""
        info, vector = self.analyze(data, min_speech)
        if vector is None:
            raise VoiceError(info["problem"])
        return info, vector


_ENGINE: VoiceEngine | None = None


def engine() -> VoiceEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = VoiceEngine()
    return _ENGINE
