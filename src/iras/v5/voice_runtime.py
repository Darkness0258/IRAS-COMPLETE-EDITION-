from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Callable, Any


@dataclass
class VoiceTurn:
    speaker_id: str
    text: str
    started_at: float
    ended_at: float
    prosody: dict[str, Any] = field(default_factory=dict)


class FullDuplexVoiceRuntime:
    """Transport-agnostic low-latency full-duplex voice coordinator.

    Audio/STT/TTS/VAD/speaker/prosody models are injected. The coordinator owns
    wake-word state and guarantees barge-in cancels current TTS before the next
    user turn is dispatched.
    """

    def __init__(self, *, wake_words: tuple[str, ...] = ("iras",)):
        self.wake_words = tuple(x.lower() for x in wake_words)
        self._tts_cancel = threading.Event()
        self._speaking = False
        self._lock = threading.RLock()
        self.turns: list[VoiceTurn] = []
        self.speaker_identifier: Callable[[bytes], str] | None = None
        self.prosody_analyzer: Callable[[bytes], dict[str, Any]] | None = None
        self.voice_activity_detector: Callable[[bytes], bool] | None = None

    @property
    def speaking(self) -> bool:
        with self._lock: return self._speaking

    def configure_analysis(self, *, speaker_identifier=None, prosody_analyzer=None, voice_activity_detector=None) -> None:
        self.speaker_identifier = speaker_identifier or self.speaker_identifier
        self.prosody_analyzer = prosody_analyzer or self.prosody_analyzer
        self.voice_activity_detector = voice_activity_detector or self.voice_activity_detector

    def detect_wake(self, text: str) -> bool:
        words = " ".join(text.lower().split())
        return any(w in words.split() for w in self.wake_words)

    def analyze_audio(self, audio: bytes) -> dict[str, Any]:
        return {
            "speech": self.voice_activity_detector(audio) if self.voice_activity_detector else None,
            "speaker_id": self.speaker_identifier(audio) if self.speaker_identifier else "unknown",
            "prosody": self.prosody_analyzer(audio) if self.prosody_analyzer else {},
        }

    def begin_speaking(self) -> threading.Event:
        with self._lock:
            self._tts_cancel = threading.Event(); self._speaking = True; return self._tts_cancel

    def finish_speaking(self) -> None:
        with self._lock: self._speaking = False

    def barge_in(self) -> bool:
        with self._lock:
            was = self._speaking; self._tts_cancel.set(); self._speaking = False; return was

    def add_turn(self, speaker_id: str, text: str, started_at: float, ended_at: float, prosody: dict[str, Any] | None = None) -> VoiceTurn:
        turn = VoiceTurn(speaker_id, text, started_at, ended_at, prosody or {}); self.turns.append(turn); return turn
