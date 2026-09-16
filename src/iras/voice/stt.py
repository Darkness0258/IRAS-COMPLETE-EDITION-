from __future__ import annotations

from collections import deque
from pathlib import Path
import os
import queue
import tempfile
import threading
import time

class Listener:
    def __init__(self, model: str = "base.en", seconds: int = 6):
        self.model_name = model
        self.seconds = seconds
        self._model = None
        self._listen_lock = threading.Lock()

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
            segments, _ = model.transcribe(str(path), vad_filter=True)
            return " ".join(
                segment.text.strip()
                for segment in segments
            ).strip()
        finally:
            try:
                path.unlink()
            except OSError:
                pass

    def listen_once(self) -> str:
        return self.listen_phrase(
            start_timeout=max(4.0, float(self.seconds)),
            max_seconds=max(8.0, float(self.seconds) * 2),
        )

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
