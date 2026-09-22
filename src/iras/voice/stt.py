from __future__ import annotations

from collections import deque
from pathlib import Path
import os
import queue
import re
import tempfile
import threading
import time

from iras.voice.multilingual_voice import whisper_language_hint


class Listener:
    def __init__(self, model: str = "base", seconds: int = 6):
        self.model_name = "base" if str(model or "").strip().lower() == "base.en" else str(model or "base")
        self.seconds = seconds
        self._model = None
        self._listen_lock = threading.Lock()
        self.last_language = ""
        self.last_language_probability = 0.0

    @staticmethod
    def _deps():
        try:
            import numpy as np
            import sounddevice as sd
            import soundfile as sf
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "Install microphone support with: pip install -e '.[voice]'"
            ) from exc
        return np, sd, sf, WhisperModel

    @staticmethod
    def list_input_devices() -> list[dict]:
        try:
            import sounddevice as sd
        except ImportError:
            return []
        devices = []
        try:
            for index, item in enumerate(sd.query_devices()):
                if int(item.get("max_input_channels", 0) or 0) <= 0:
                    continue
                devices.append(
                    {
                        "index": index,
                        "name": str(item.get("name") or ""),
                        "channels": int(item.get("max_input_channels", 0) or 0),
                        "default_samplerate": float(item.get("default_samplerate", 0) or 0),
                    }
                )
        except Exception:
            return []
        return devices

    @classmethod
    def microphone_status(cls) -> dict:
        devices = cls.list_input_devices()
        selected = os.getenv("IRAS_MIC_DEVICE", "").strip()
        return {
            "available": bool(devices),
            "count": len(devices),
            "selected": selected or "system-default",
            "devices": devices[:24],
        }

    @staticmethod
    def _input_device():
        raw = os.getenv("IRAS_MIC_DEVICE", "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return raw

    def _ensure_model(self, WhisperModel):
        if self._model is None:
            self._model = WhisperModel(
                self.model_name,
                device="cpu",
                compute_type="int8",
            )
        return self._model

    def _transcribe(self, audio, sample_rate: int) -> str:
        _np, _sd, sf, WhisperModel = self._deps()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            path = Path(handle.name)
        try:
            sf.write(path, audio, sample_rate)
            model = self._ensure_model(WhisperModel)
            segments, info = model.transcribe(
                str(path),
                vad_filter=True,
                language=whisper_language_hint(),
            )
            self.last_language = str(getattr(info, "language", "") or "")
            try:
                self.last_language_probability = float(
                    getattr(info, "language_probability", 0.0) or 0.0
                )
            except (TypeError, ValueError):
                self.last_language_probability = 0.0
            return " ".join(
                segment.text.strip()
                for segment in segments
            ).strip()
        finally:
            try:
                path.unlink()
            except OSError:
                pass

    @staticmethod
    def _normalized(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9']+", str(text or "").casefold()))

    @classmethod
    def _contains_wake(cls, text: str, wake_words: tuple[str, ...]) -> bool:
        words = set(re.findall(r"[a-z0-9']+", str(text or "").casefold()))
        return any(str(w).casefold() in words for w in wake_words)

    @classmethod
    def _end_requested(cls, text: str, end_phrases: tuple[str, ...]) -> bool:
        normalized = cls._normalized(text)
        return any(cls._normalized(p) in normalized for p in end_phrases if cls._normalized(p))

    @staticmethod
    def _strip_wake(text: str, wake_words: tuple[str, ...]) -> str:
        value = str(text or "").strip()
        for wake in wake_words:
            value = re.sub(rf"(?i)\b{re.escape(str(wake))}\b[\s,:;-]*", "", value, count=1)
        return " ".join(value.split())

    @classmethod
    def _strip_end(cls, text: str, end_phrases: tuple[str, ...]) -> str:
        value = str(text or "").strip()
        normalized = cls._normalized(value)
        for phrase in end_phrases:
            norm = cls._normalized(phrase)
            if norm and norm in normalized:
                tokens = norm.split()
                pattern = r"(?i)\b" + r"[\s,.'’!?-]+".join(map(re.escape, tokens)) + r"\b.*$"
                value = re.sub(pattern, "", value).strip(" ,.!?;:-")
                break
        return " ".join(value.split())

    @staticmethod
    def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
        try:
            value = float(os.getenv(name, str(default)))
        except ValueError:
            value = default
        return max(minimum, min(maximum, value))

    def listen_once(self) -> str:
        enabled = os.getenv("IRAS_WAKE_SESSION", "true").strip().lower() not in {
            "0", "false", "no", "off"
        }
        if not enabled:
            return self.listen_phrase(
                start_timeout=max(4.0, float(self.seconds)),
                max_seconds=max(8.0, float(self.seconds) * 2),
            )
        wake_words = tuple(
            x.strip().casefold()
            for x in os.getenv("IRAS_WAKE_WORDS", "iras").split(",")
            if x.strip()
        ) or ("iras",)
        end_phrases = tuple(
            x.strip()
            for x in os.getenv(
                "IRAS_WAKE_END_PHRASES",
                "done that's all|that's all|done iras|end session",
            ).split("|")
            if x.strip()
        )
        return self.listen_session(
            wake_words=wake_words,
            end_phrases=end_phrases,
            idle_seconds=self._env_float("IRAS_WAKE_IDLE_SECONDS", 3.0, 1.0, 10.0),
            active_seconds=self._env_float("IRAS_WAKE_ACTIVE_SECONDS", 30.0, 5.0, 120.0),
        )

    def listen_session(
        self,
        *,
        wake_words: tuple[str, ...] = ("iras",),
        end_phrases: tuple[str, ...] = ("done that's all", "that's all", "done iras", "end session"),
        idle_seconds: float = 3.0,
        active_seconds: float = 30.0,
    ) -> str:
        """Capture one short command, extending to a wake-word command session.

        The microphone waits only ``idle_seconds`` for the first utterance. If that
        utterance contains a wake word, IRAS keeps accepting phrases until the
        ``active_seconds`` deadline or an end phrase such as "done that's all".
        """
        idle_seconds = max(1.0, float(idle_seconds))
        active_seconds = max(idle_seconds, float(active_seconds))
        first = self.listen_phrase(
            start_timeout=idle_seconds,
            max_seconds=max(3.0, min(12.0, float(self.seconds) * 2)),
        )
        if not first:
            return ""
        woke = self._contains_wake(first, wake_words)
        ending = self._end_requested(first, end_phrases)
        first = self._strip_end(self._strip_wake(first, wake_words), end_phrases)
        if ending or not woke:
            return first

        parts = [first] if first else []
        deadline = time.monotonic() + active_seconds
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            phrase = self.listen_phrase(
                start_timeout=min(idle_seconds, remaining),
                max_seconds=max(1.0, min(max(4.0, float(self.seconds) * 2), remaining)),
            )
            if not phrase:
                continue
            ending = self._end_requested(phrase, end_phrases)
            cleaned = self._strip_end(self._strip_wake(phrase, wake_words), end_phrases)
            if cleaned:
                parts.append(cleaned)
            if ending:
                break
        return " ".join(parts).strip()

    def listen_phrase(
        self,
        *,
        start_timeout: float = 2.0,
        max_seconds: float = 12.0,
        silence_seconds: float = 0.75,
        min_speech_seconds: float = 0.20,
        energy_threshold: float = 0.012,
        noise_multiplier: float = 3.0,
        sample_rate: int = 16000,
    ) -> str:
        np, sd, _sf, _WhisperModel = self._deps()
        with self._listen_lock:
            audio_queue: queue.Queue = queue.Queue()
            block_seconds = 0.03
            blocksize = int(sample_rate * block_seconds)

            def callback(indata, frames, time_info, status):
                del frames, time_info, status
                audio_queue.put(indata.copy())

            pre_roll = deque(maxlen=max(1, int(0.30 / block_seconds)))
            noise_values = []
            collected = []
            speech_started = False
            speech_started_at = 0.0
            silence_for = 0.0
            started_at = time.monotonic()
            hard_deadline = started_at + start_timeout + max_seconds

            with sd.InputStream(
                device=self._input_device(),
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=blocksize,
                callback=callback,
            ):
                while time.monotonic() < hard_deadline:
                    try:
                        block = audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue

                    rms = float(np.sqrt(np.mean(np.square(block))))
                    elapsed = time.monotonic() - started_at

                    if not speech_started and elapsed < 0.45:
                        noise_values.append(rms)

                    noise_floor = (
                        float(np.median(noise_values))
                        if noise_values else 0.0
                    )
                    threshold = max(
                        float(energy_threshold),
                        noise_floor * float(noise_multiplier),
                    )

                    if not speech_started:
                        pre_roll.append(block)
                        if rms >= threshold:
                            speech_started = True
                            speech_started_at = time.monotonic()
                            collected.extend(list(pre_roll))
                            silence_for = 0.0
                        elif elapsed >= start_timeout:
                            return ""
                        continue

                    collected.append(block)
                    silence_for = (
                        silence_for + block_seconds
                        if rms < threshold else 0.0
                    )
                    spoken_for = time.monotonic() - speech_started_at

                    if (
                        spoken_for >= min_speech_seconds
                        and silence_for >= silence_seconds
                    ):
                        break
                    if spoken_for >= max_seconds:
                        break

            if not collected:
                return ""

            audio = np.concatenate(collected, axis=0)
            return self._transcribe(audio, sample_rate)
