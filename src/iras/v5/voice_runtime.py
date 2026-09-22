from __future__ import annotations

from dataclasses import dataclass, field
import queue
import re
import threading
import time
from typing import Callable, Any


@dataclass
class VoiceTurn:
    speaker_id: str
    text: str
    started_at: float
    ended_at: float
    prosody: dict[str, Any] = field(default_factory=dict)


class FullDuplexVoiceRuntime:
    """Low-latency voice coordinator with wake-word state and barge-in.

    Idle speech is treated as short wake detection. Saying IRAS opens a bounded
    30-second command session. An end phrase closes that session immediately.
    Audio I/O remains injectable so local Whisper/Edge TTS and alternate engines
    can share the same state machine.
    """

    def __init__(
        self,
        *,
        wake_words: tuple[str, ...] = ("iras",),
        idle_window_seconds: float = 3.0,
        active_window_seconds: float = 30.0,
        end_phrases: tuple[str, ...] = ("done that's all", "that's all", "done iras", "end session"),
    ):
        self.wake_words = tuple(x.casefold().strip() for x in wake_words if str(x).strip())
        self.idle_window_seconds = max(1.0, float(idle_window_seconds))
        self.active_window_seconds = max(self.idle_window_seconds, float(active_window_seconds))
        self.end_phrases = tuple(self._normalize(x) for x in end_phrases if str(x).strip())
        self._tts_cancel = threading.Event()
        self._speaking = False
        self._lock = threading.RLock()
        self.turns: list[VoiceTurn] = []
        self.speaker_identifier: Callable[[bytes], str] | None = None
        self.prosody_analyzer: Callable[[bytes], dict[str, Any]] | None = None
        self.voice_activity_detector: Callable[[bytes], bool] | None = None
        self.transcriber: Callable[[bytes], str] | None = None
        self.dispatcher: Callable[[str, dict[str, Any]], str] | None = None
        self.synthesizer: Callable[[str, threading.Event], Any] | None = None
        self._q: queue.Queue[tuple[bytes, float]] = queue.Queue(maxsize=64)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.require_wake_word = True
        self._awake_until = 0.0

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9']+", str(text or "").casefold()))

    @property
    def speaking(self) -> bool:
        with self._lock:
            return self._speaking

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def awake(self) -> bool:
        return time.time() <= self._awake_until

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "speaking": self.speaking,
            "awake": self.awake,
            "wake_words": list(self.wake_words),
            "idle_window_seconds": self.idle_window_seconds,
            "active_window_seconds": self.active_window_seconds,
            "end_phrases": list(self.end_phrases),
            "require_wake_word": self.require_wake_word,
            "turn_count": len(self.turns),
        }

    def configure_analysis(self, *, speaker_identifier=None, prosody_analyzer=None, voice_activity_detector=None) -> None:
        self.speaker_identifier = speaker_identifier or self.speaker_identifier
        self.prosody_analyzer = prosody_analyzer or self.prosody_analyzer
        self.voice_activity_detector = voice_activity_detector or self.voice_activity_detector

    def configure_pipeline(self, *, transcriber=None, dispatcher=None, synthesizer=None) -> None:
        self.transcriber = transcriber or self.transcriber
        self.dispatcher = dispatcher or self.dispatcher
        self.synthesizer = synthesizer or self.synthesizer

    def detect_wake(self, text: str) -> bool:
        words = set(re.findall(r"[a-z0-9']+", str(text or "").casefold()))
        return any(wake in words for wake in self.wake_words)

    def end_requested(self, text: str) -> bool:
        normalized = self._normalize(text)
        return any(phrase and phrase in normalized for phrase in self.end_phrases)

    def strip_control_phrases(self, text: str) -> str:
        value = str(text or "").strip()
        for wake in self.wake_words:
            value = re.sub(rf"(?i)\b{re.escape(wake)}\b[\s,:;-]*", "", value, count=1)
        normalized = self._normalize(value)
        for phrase in self.end_phrases:
            if phrase and phrase in normalized:
                tokens = phrase.split()
                pattern = r"(?i)\b" + r"[\s,.'’!?-]+".join(map(re.escape, tokens)) + r"\b.*$"
                value = re.sub(pattern, "", value).strip(" ,.!?;:-")
                break
        return " ".join(value.split())

    def analyze_audio(self, audio: bytes) -> dict[str, Any]:
        return {
            "speech": self.voice_activity_detector(audio) if self.voice_activity_detector else None,
            "speaker_id": self.speaker_identifier(audio) if self.speaker_identifier else "unknown",
            "prosody": self.prosody_analyzer(audio) if self.prosody_analyzer else {},
        }

    def begin_speaking(self) -> threading.Event:
        with self._lock:
            self._tts_cancel = threading.Event()
            self._speaking = True
            return self._tts_cancel

    def finish_speaking(self) -> None:
        with self._lock:
            self._speaking = False

    def barge_in(self) -> bool:
        with self._lock:
            was = self._speaking
            self._tts_cancel.set()
            self._speaking = False
            return was

    def add_turn(
        self,
        speaker_id: str,
        text: str,
        started_at: float,
        ended_at: float,
        prosody: dict[str, Any] | None = None,
    ) -> VoiceTurn:
        turn = VoiceTurn(speaker_id, text, started_at, ended_at, prosody or {})
        self.turns.append(turn)
        self.turns = self.turns[-500:]
        return turn

    def feed_audio(self, audio: bytes, *, started_at: float | None = None) -> bool:
        if not audio:
            return False
        if self.speaking:
            self.barge_in()
        try:
            self._q.put_nowait((audio, started_at or time.time()))
            return True
        except queue.Full:
            return False

    def _handle(self, audio: bytes, started: float) -> None:
        meta = self.analyze_audio(audio)
        if meta.get("speech") is False or not self.transcriber:
            return
        raw_text = str(self.transcriber(audio) or "").strip()
        if not raw_text:
            return

        woke = self.detect_wake(raw_text)
        ending = self.end_requested(raw_text)
        if woke:
            self._awake_until = time.time() + self.active_window_seconds
        if self.require_wake_word and not woke and not self.awake:
            return

        text = self.strip_control_phrases(raw_text)
        if ending:
            self._awake_until = 0.0
        if not text:
            return

        speaker = str(meta.get("speaker_id") or "unknown")
        self.add_turn(speaker, text, started, time.time(), dict(meta.get("prosody") or {}))
        if not self.dispatcher:
            return
        reply = str(
            self.dispatcher(
                text,
                {
                    "speaker_id": speaker,
                    "prosody": meta.get("prosody") or {},
                    "wake_word": woke,
                    "voice_session_active": self.awake,
                },
            )
            or ""
        )
        if reply and self.synthesizer:
            cancel = self.begin_speaking()
            try:
                self.synthesizer(reply, cancel)
            finally:
                self.finish_speaking()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    audio, started = self._q.get(timeout=0.25)
                except queue.Empty:
                    continue
                try:
                    self._handle(audio, started)
                except Exception:
                    continue

        self._thread = threading.Thread(target=loop, name="iras-v5-voice", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._awake_until = 0.0
        self.barge_in()
