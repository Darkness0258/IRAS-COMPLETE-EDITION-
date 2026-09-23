from __future__ import annotations

from collections import deque
from pathlib import Path
import math
import difflib
import os
import queue
import re
import tempfile
import threading
import time
from typing import Any

from iras.voice.multilingual_voice import whisper_language_hint


_DEVICE_UNSET = object()


class Listener:
    """Reliable local microphone capture + Faster-Whisper transcription.

    Device policy is intentionally conservative on Windows:
    * an explicit ``IRAS_MIC_DEVICE`` is tried first;
    * otherwise physical Realtek microphone endpoints are preferred;
    * WASAPI is preferred over legacy wrappers when the same device appears
      through several PortAudio host APIs;
    * virtual/loopback inputs are strongly de-prioritized;
    * capture failures fall through to the next viable input endpoint.
    """

    def __init__(self, model: str = "base", seconds: int = 6):
        self.model_name = "base" if str(model or "").strip().lower() == "base.en" else str(model or "base")
        self.seconds = seconds
        self._model = None
        self._listen_lock = threading.Lock()
        self.last_language = ""
        self.last_language_probability = 0.0
        self.last_device: int | str | None = None
        self.last_device_name = ""
        self.last_sample_rate = 0
        self.last_rms = 0.0
        self.last_peak = 0.0
        self.last_noise_floor = 0.0
        self.last_energy_threshold = 0.0
        self.last_capture_error = ""
        self.last_transcription_rejected_reason = ""
        self.last_transcription_attempts = 0
        self.last_clipping_ratio = 0.0

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
    def _truthy_env(name: str, default: bool = False) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() not in {"", "0", "false", "no", "off"}

    @staticmethod
    def _hostapi_name(sd, hostapi_index: Any) -> str:
        try:
            info = sd.query_hostapis(int(hostapi_index))
            if isinstance(info, dict):
                return str(info.get("name") or "")
        except Exception:
            pass
        return ""

    @staticmethod
    def _default_input_index(sd) -> int | None:
        try:
            default = getattr(getattr(sd, "default", None), "device", None)
            if default is None:
                return None
            try:
                value = default[0]
            except Exception:
                value = default
            value = int(value)
            return value if value >= 0 else None
        except Exception:
            return None

    @staticmethod
    def _device_score(name: str, hostapi: str, *, is_default: bool = False) -> int:
        n = str(name or "").casefold()
        h = str(hostapi or "").casefold()
        score = 0

        # Prefer the laptop's physical Realtek microphone endpoints.
        if "realtek" in n:
            score += 140
        if "microphone array" in n or "mic array" in n:
            score += 45
        elif "microphone" in n:
            score += 35
        elif re.search(r"\bmic\b", n):
            score += 25
        if "headset" in n:
            score += 12

        # Shared-mode WASAPI is usually the most reliable modern Windows path.
        if "wasapi" in h:
            score += 40
        elif "directsound" in h:
            score += 18
        elif "mme" in h:
            score += 8
        elif "wdm-ks" in h or "wdm/ks" in h:
            score -= 8

        if is_default:
            score += 24

        # Avoid loopback/virtual endpoints unless the user explicitly selects one.
        if "wo mic" in n:
            score -= 95
        if "stereo mix" in n or "what u hear" in n or "loopback" in n:
            score -= 140
        if "line in" in n:
            score -= 55
        if any(token in n for token in ("voicemeeter", "virtual", "vb-audio", "cable input", "cable output")):
            score -= 75
        if "mapper" in n:
            score -= 20

        return score

    @classmethod
    def _enumerate_input_devices(cls, sd) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        default_index = cls._default_input_index(sd)
        try:
            raw_devices = sd.query_devices()
        except Exception:
            return result

        for index, item in enumerate(raw_devices):
            try:
                channels = int(item.get("max_input_channels", 0) or 0)
            except Exception:
                channels = 0
            if channels <= 0:
                continue

            name = str(item.get("name") or "")
            hostapi_index = item.get("hostapi")
            hostapi_name = cls._hostapi_name(sd, hostapi_index)
            try:
                default_samplerate = float(item.get("default_samplerate", 0) or 0)
            except Exception:
                default_samplerate = 0.0

            result.append(
                {
                    "index": index,
                    "name": name,
                    "channels": channels,
                    "default_samplerate": default_samplerate,
                    "hostapi": hostapi_name,
                    "hostapi_index": hostapi_index,
                    "is_default": index == default_index,
                    "score": cls._device_score(
                        name,
                        hostapi_name,
                        is_default=index == default_index,
                    ),
                }
            )
        return result

    @classmethod
    def list_input_devices(cls) -> list[dict]:
        try:
            import sounddevice as sd
        except ImportError:
            return []
        try:
            return cls._enumerate_input_devices(sd)
        except Exception:
            return []

    @staticmethod
    def _input_device():
        """Backward-compatible raw environment parser.

        New code should use ``select_input_device`` so duplicate Windows device
        names can be resolved deterministically.
        """
        raw = os.getenv("IRAS_MIC_DEVICE", "").strip()
        if not raw or raw.casefold() in {"auto", "default", "system-default"}:
            return None
        try:
            return int(raw)
        except ValueError:
            return raw

    @classmethod
    def _explicit_device(cls, devices: list[dict[str, Any]]) -> int | str | None:
        raw = os.getenv("IRAS_MIC_DEVICE", "").strip()
        if not raw or raw.casefold() in {"auto", "default", "system-default"}:
            return None

        try:
            wanted_index = int(raw)
        except ValueError:
            wanted_index = None

        if wanted_index is not None:
            if any(int(dev["index"]) == wanted_index for dev in devices):
                return wanted_index
            # Keep historical behavior: let PortAudio produce the useful error,
            # then the fallback list can recover unless strict mode is enabled.
            return wanted_index

        needle = raw.casefold()
        exact = [dev for dev in devices if str(dev["name"]).casefold() == needle]
        matches = exact or [dev for dev in devices if needle in str(dev["name"]).casefold()]
        if matches:
            matches.sort(key=lambda dev: (int(dev["score"]), bool(dev["is_default"])), reverse=True)
            return int(matches[0]["index"])
        return raw

    @classmethod
    def ranked_input_devices(cls, sd=None) -> list[dict[str, Any]]:
        if sd is None:
            try:
                import sounddevice as sd
            except ImportError:
                return []
        devices = cls._enumerate_input_devices(sd)
        return sorted(
            devices,
            key=lambda dev: (int(dev["score"]), bool(dev["is_default"]), -int(dev["index"])),
            reverse=True,
        )

    @classmethod
    def select_input_device(cls, sd=None) -> int | str | None:
        if sd is None:
            try:
                import sounddevice as sd
            except ImportError:
                return None
        ranked = cls.ranked_input_devices(sd)
        explicit = cls._explicit_device(ranked)
        if explicit is not None:
            return explicit
        if ranked:
            return int(ranked[0]["index"])
        return None

    @classmethod
    def _candidate_input_devices(cls, sd) -> list[int | str | None]:
        ranked = cls.ranked_input_devices(sd)
        explicit = cls._explicit_device(ranked)
        strict = cls._truthy_env("IRAS_MIC_STRICT", False)
        candidates: list[int | str | None] = []

        if explicit is not None:
            candidates.append(explicit)
            if strict:
                return candidates

        for dev in ranked:
            index = int(dev["index"])
            if index not in candidates:
                candidates.append(index)

        # System default is a useful last chance if PortAudio's device inventory
        # is unusual or a device changed after enumeration.
        if None not in candidates:
            candidates.append(None)
        return candidates or [None]

    @classmethod
    def _device_info(cls, sd, device: int | str | None) -> dict[str, Any]:
        try:
            item = sd.query_devices(device, "input")
            return dict(item) if isinstance(item, dict) else {}
        except Exception:
            return {}

    @classmethod
    def _device_name(cls, sd, device: int | str | None) -> str:
        info = cls._device_info(sd, device)
        return str(info.get("name") or ("system-default" if device is None else device))

    @classmethod
    def microphone_status(cls) -> dict:
        selected_raw = os.getenv("IRAS_MIC_DEVICE", "").strip()
        try:
            import sounddevice as sd
            devices = cls.ranked_input_devices(sd)
            explicit = cls._explicit_device(devices)
            selected_device = explicit if explicit is not None else (
                int(devices[0]["index"]) if devices else None
            )
            selected_name = cls._device_name(sd, selected_device)
        except Exception:
            devices = cls.list_input_devices()
            selected_device = cls._input_device()
            selected_name = str(selected_device or "system-default")

        return {
            "available": bool(devices),
            "count": len(devices),
            "configured": selected_raw or "auto",
            "selected": selected_device if selected_device is not None else "system-default",
            "selected_name": selected_name,
            "devices": devices[:32],
        }

    @classmethod
    def _supported_sample_rate(cls, sd, requested: int, device=_DEVICE_UNSET) -> int:
        if device is _DEVICE_UNSET:
            device = cls._input_device()
        requested = max(8000, int(requested))

        rates: list[int] = [requested]
        try:
            info = sd.query_devices(device, "input")
            fallback = int(round(float(info.get("default_samplerate", requested) or requested)))
            if fallback >= 8000 and fallback not in rates:
                rates.append(fallback)
        except Exception:
            pass

        for fallback in (48000, 44100, 32000, 24000, 22050, 16000, 8000):
            if fallback not in rates:
                rates.append(fallback)

        last_rate = requested
        for rate in rates:
            last_rate = rate
            try:
                sd.check_input_settings(
                    device=device,
                    channels=1,
                    dtype="float32",
                    samplerate=rate,
                )
                return rate
            except Exception:
                continue
        return last_rate

    @staticmethod
    def _audio_metrics(np, audio) -> tuple[float, float, float]:
        if audio is None or getattr(audio, "size", 0) == 0:
            return 0.0, 0.0, -120.0
        values = np.asarray(audio, dtype="float32")
        rms = float(np.sqrt(np.mean(np.square(values))))
        peak = float(np.max(np.abs(values)))
        dbfs = 20.0 * math.log10(max(rms, 1e-6))
        return rms, peak, max(-120.0, dbfs)

    @classmethod
    def test_input_level(
        cls,
        seconds: float = 0.8,
        *,
        device=_DEVICE_UNSET,
        sample_rate: int = 16000,
    ) -> dict[str, Any]:
        """Capture a short raw level sample without invoking Whisper."""
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("Install microphone support with: pip install -e '.[voice]'") from exc

        if device is _DEVICE_UNSET:
            device = cls.select_input_device(sd)
        rate = cls._supported_sample_rate(sd, sample_rate, device=device)
        seconds = max(0.15, min(5.0, float(seconds)))
        frames_left = max(1, int(rate * seconds))
        chunks = []
        overflowed = False
        blocksize = max(128, int(rate * 0.05))

        with sd.InputStream(
            device=device,
            samplerate=rate,
            channels=1,
            dtype="float32",
            blocksize=blocksize,
        ) as stream:
            while frames_left > 0:
                count = min(blocksize, frames_left)
                block, over = stream.read(count)
                chunks.append(block.copy())
                overflowed = overflowed or bool(over)
                frames_left -= count

        audio = np.concatenate(chunks, axis=0) if chunks else np.zeros((0, 1), dtype="float32")
        rms, peak, dbfs = cls._audio_metrics(np, audio)
        if peak >= 0.02 or rms >= 0.006:
            signal = "strong"
        elif peak >= 0.006 or rms >= 0.002:
            signal = "present"
        elif peak >= 0.0015 or rms >= 0.0005:
            signal = "very-low"
        else:
            signal = "silent"

        return {
            "device": device if device is not None else "system-default",
            "name": cls._device_name(sd, device),
            "sample_rate": rate,
            "seconds": seconds,
            "rms": rms,
            "peak": peak,
            "dbfs": dbfs,
            "signal": signal,
            "overflowed": overflowed,
        }

    def _ensure_model(self, WhisperModel):
        if self._model is None:
            self._model = WhisperModel(
                self.model_name,
                device="cpu",
                compute_type="int8",
            )
        return self._model

    @staticmethod
    def _stt_prompt() -> str:
        custom = os.getenv("IRAS_STT_PROMPT", "").strip()
        if custom:
            return custom
        return (
            "IRAS, Iris. The speaker may use English, Urdu, Roman Urdu, or code-switch "
            "between them. Preserve commands, application names, people names, and technical terms accurately."
        )

    @staticmethod
    def _stt_hotwords() -> str:
        return (
            os.getenv(
                "IRAS_STT_HOTWORDS",
                "IRAS Iris Eris Windows Chrome Spotify VS Code GitHub PowerShell Python",
            ).strip()
        )

    @staticmethod
    def _transcript_key(text: str) -> str:
        chars = [ch.casefold() if ch.isalnum() else " " for ch in str(text or "")]
        return " ".join("".join(chars).split())

    def _transcript_rejection_reason(self, text: str) -> str:
        key = self._transcript_key(text)
        if not key:
            return "punctuation/noise only"
        prompt_key = self._transcript_key(self._stt_prompt())
        if len(key) >= 28 and prompt_key:
            ratio = difflib.SequenceMatcher(None, key, prompt_key).ratio()
            if ratio >= 0.68 or key in prompt_key or prompt_key in key:
                return "Whisper echoed the recognition prompt instead of the microphone"
        words = key.split()
        if len(words) >= 8 and len(set(words)) <= 1:
            return "repeated-token hallucination"
        return ""

    def _transcribe(self, audio, sample_rate: int) -> str:
        _np, _sd, sf, WhisperModel = self._deps()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            path = Path(handle.name)
        try:
            sf.write(path, audio, sample_rate)
            model = self._ensure_model(WhisperModel)
            hint = whisper_language_hint()
            self.last_transcription_rejected_reason = ""
            self.last_transcription_attempts = 0

            def run_pass(*, vad_filter: bool, use_context: bool, language):
                kwargs = {
                    "vad_filter": vad_filter,
                    "language": language,
                    "condition_on_previous_text": False,
                    "beam_size": 5,
                    "temperature": 0.0,
                }
                if use_context:
                    kwargs["initial_prompt"] = self._stt_prompt()
                    hotwords = self._stt_hotwords()
                    if hotwords:
                        kwargs["hotwords"] = hotwords
                try:
                    segments, info = model.transcribe(str(path), **kwargs)
                except TypeError:
                    kwargs.pop("hotwords", None)
                    kwargs.pop("temperature", None)
                    segments, info = model.transcribe(str(path), **kwargs)
                text = " ".join(segment.text.strip() for segment in segments).strip()
                self.last_transcription_attempts += 1
                return text, info

            attempts = [(True, True, hint), (False, False, hint)]
            if hint is None:
                attempts.extend([(False, False, "en"), (False, False, "ur")])

            last_info = None
            last_reason = ""
            for vad_filter, use_context, language in attempts:
                text, info = run_pass(
                    vad_filter=vad_filter, use_context=use_context, language=language
                )
                last_info = info
                reason = self._transcript_rejection_reason(text)
                if text and not reason:
                    self.last_language = str(getattr(info, "language", "") or language or "")
                    try:
                        self.last_language_probability = float(
                            getattr(info, "language_probability", 0.0) or 0.0
                        )
                    except (TypeError, ValueError):
                        self.last_language_probability = 0.0
                    self.last_transcription_rejected_reason = ""
                    return text
                last_reason = reason or "empty transcription"

            if last_info is not None:
                self.last_language = str(getattr(last_info, "language", "") or "")
                try:
                    self.last_language_probability = float(
                        getattr(last_info, "language_probability", 0.0) or 0.0
                    )
                except (TypeError, ValueError):
                    self.last_language_probability = 0.0
            self.last_transcription_rejected_reason = last_reason
            return ""
        finally:
            try:
                path.unlink()
            except OSError:
                pass

    @staticmethod
    def _normalized(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9']+", str(text or "").casefold()))

    @staticmethod
    def _wake_aliases(wake_words: tuple[str, ...]) -> tuple[str, ...]:
        aliases: list[str] = []
        for wake in wake_words:
            value = str(wake or "").strip()
            if value and value not in aliases:
                aliases.append(value)
            if value.casefold() == "iras":
                for extra in (
                    "iris",
                    "eris",
                    "eras",
                    "eye ris",
                    "eye ras",
                    "i r a s",
                    "آئرس",
                    "ایرس",
                ):
                    if extra not in aliases:
                        aliases.append(extra)
        return tuple(aliases)

    @classmethod
    def _contains_wake(cls, text: str, wake_words: tuple[str, ...]) -> bool:
        value = str(text or "").casefold()
        for wake in cls._wake_aliases(wake_words):
            alias = str(wake).casefold().strip()
            if not alias:
                continue
            if re.search(r"[a-z0-9]", alias):
                tokens = re.findall(r"[a-z0-9']+", alias)
                if not tokens:
                    continue
                pattern = r"(?<![a-z0-9])" + r"[\s-]*".join(map(re.escape, tokens)) + r"(?![a-z0-9])"
                if re.search(pattern, value, flags=re.IGNORECASE):
                    return True
            elif alias in value:
                return True
        return False

    @classmethod
    def _end_requested(cls, text: str, end_phrases: tuple[str, ...]) -> bool:
        normalized = cls._normalized(text)
        return any(cls._normalized(p) in normalized for p in end_phrases if cls._normalized(p))

    @classmethod
    def _strip_wake(cls, text: str, wake_words: tuple[str, ...]) -> str:
        value = str(text or "").strip()
        for wake in sorted(cls._wake_aliases(wake_words), key=len, reverse=True):
            alias = str(wake or "").strip()
            if not alias:
                continue
            if re.search(r"[a-z0-9]", alias, flags=re.IGNORECASE):
                tokens = re.findall(r"[a-z0-9']+", alias.casefold())
                if not tokens:
                    continue
                pattern = r"(?i)(?<![a-z0-9])" + r"[\s-]*".join(map(re.escape, tokens)) + r"(?![a-z0-9])[\s,:;-]*"
            else:
                pattern = re.escape(alias) + r"[\s,:;-]*"
            value = re.sub(pattern, "", value, count=1).strip()
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
        """Capture one short command, extending to a wake-word command session."""
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

    def _capture_phrase_on_device(
        self,
        np,
        sd,
        *,
        device: int | str | None,
        start_timeout: float,
        max_seconds: float,
        silence_seconds: float,
        min_speech_seconds: float,
        energy_threshold: float,
        noise_multiplier: float,
        sample_rate: int,
    ):
        sample_rate = self._supported_sample_rate(sd, sample_rate, device=device)
        audio_queue: queue.Queue = queue.Queue(maxsize=256)
        block_seconds = 0.03
        blocksize = max(128, int(sample_rate * block_seconds))
        callback_overflow = False

        def callback(indata, frames, time_info, status):
            nonlocal callback_overflow
            del frames, time_info
            if status:
                callback_overflow = True
            try:
                audio_queue.put_nowait(indata.copy())
            except queue.Full:
                callback_overflow = True
                try:
                    audio_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    audio_queue.put_nowait(indata.copy())
                except queue.Full:
                    pass

        pre_roll = deque(maxlen=max(1, int(0.36 / block_seconds)))
        noise_values = deque(maxlen=max(8, int(0.90 / block_seconds)))
        collected = []
        speech_started = False
        speech_started_at = 0.0
        silence_for = 0.0
        started_at = time.monotonic()
        hard_deadline = started_at + start_timeout + max_seconds
        last_threshold = float(energy_threshold)
        observed_peak = 0.0

        with sd.InputStream(
            device=device,
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
                peak = float(np.max(np.abs(block)))
                observed_peak = max(observed_peak, peak)
                elapsed = time.monotonic() - started_at

                # IMPORTANT: calculate the speech threshold from *previously
                # observed quiet blocks*. The old RC12 code inserted the current
                # block first; when the user started speaking immediately, their
                # voice became the noise floor and the threshold jumped above it.
                noise_floor = float(np.median(noise_values)) if noise_values else 0.0
                threshold = max(float(energy_threshold), noise_floor * float(noise_multiplier))
                last_threshold = threshold

                if not speech_started:
                    pre_roll.append(block)
                    if rms >= threshold:
                        speech_started = True
                        speech_started_at = time.monotonic()
                        collected.extend(list(pre_roll))
                        silence_for = 0.0
                    else:
                        # Only confirmed sub-threshold blocks become background
                        # calibration data, so speech can never poison calibration.
                        noise_values.append(rms)
                        if elapsed >= start_timeout:
                            self.last_device = device
                            self.last_device_name = self._device_name(sd, device)
                            self.last_sample_rate = sample_rate
                            self.last_rms = rms
                            self.last_peak = observed_peak
                            self.last_noise_floor = noise_floor
                            self.last_energy_threshold = threshold
                            return None
                    continue

                collected.append(block)
                # Hysteresis: use a lower end threshold once speech has started
                # so soft syllables are not chopped off.
                end_threshold = max(float(energy_threshold) * 0.55, threshold * 0.55)
                silence_for = silence_for + block_seconds if rms < end_threshold else 0.0
                spoken_for = time.monotonic() - speech_started_at

                if spoken_for >= min_speech_seconds and silence_for >= silence_seconds:
                    break
                if spoken_for >= max_seconds:
                    break

        self.last_device = device
        self.last_device_name = self._device_name(sd, device)
        self.last_sample_rate = sample_rate
        self.last_noise_floor = float(np.median(noise_values)) if noise_values else 0.0
        self.last_energy_threshold = last_threshold

        if not collected:
            self.last_rms = 0.0
            self.last_peak = observed_peak
            return None

        audio = np.concatenate(collected, axis=0)
        rms, peak, _dbfs = self._audio_metrics(np, audio)
        self.last_rms = rms
        self.last_peak = peak
        try:
            self.last_clipping_ratio = float(np.mean(np.abs(audio) >= 0.995))
        except Exception:
            self.last_clipping_ratio = 0.0
        if callback_overflow:
            self.last_capture_error = "PortAudio reported an input overflow during capture."
        return audio, sample_rate

    def listen_phrase(
        self,
        *,
        start_timeout: float = 2.0,
        max_seconds: float = 12.0,
        silence_seconds: float = 0.75,
        min_speech_seconds: float = 0.20,
        energy_threshold: float = 0.004,
        noise_multiplier: float = 2.6,
        sample_rate: int = 16000,
    ) -> str:
        np, sd, _sf, _WhisperModel = self._deps()
        with self._listen_lock:
            self.last_capture_error = ""
            candidates = self._candidate_input_devices(sd)
            last_exc: Exception | None = None

            for device in candidates:
                try:
                    captured = self._capture_phrase_on_device(
                        np,
                        sd,
                        device=device,
                        start_timeout=start_timeout,
                        max_seconds=max_seconds,
                        silence_seconds=silence_seconds,
                        min_speech_seconds=min_speech_seconds,
                        energy_threshold=self._env_float(
                            "IRAS_MIC_ENERGY_THRESHOLD",
                            energy_threshold,
                            0.0005,
                            0.20,
                        ),
                        noise_multiplier=self._env_float(
                            "IRAS_MIC_NOISE_MULTIPLIER",
                            noise_multiplier,
                            1.2,
                            8.0,
                        ),
                        sample_rate=sample_rate,
                    )
                except Exception as exc:
                    last_exc = exc
                    self.last_capture_error = f"{type(exc).__name__}: {exc}"
                    continue

                # A valid, opened input with no speech should not serially wait on
                # every duplicate endpoint; return promptly and let the next
                # hands-free cycle try again.
                if captured is None:
                    return ""

                audio, actual_rate = captured
                return self._transcribe(audio, actual_rate)

            if last_exc is not None:
                raise RuntimeError(
                    "No usable microphone input could be opened. "
                    f"Last error: {type(last_exc).__name__}: {last_exc}"
                ) from last_exc
            return ""
