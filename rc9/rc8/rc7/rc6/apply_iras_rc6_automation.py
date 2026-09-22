from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

EXPECTED_HEAD = "a5dbaf36e3a692212c246b1880af674d057ae26b"
MARKER = "IRAS_RC6_AUTOMATION_VOICE"

AUTOMATION_ENGINE = r'''from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .common import EventBus, SQLiteDB, new_id, utc_now


PERMISSION_MODES = ("read_only", "safe_action", "system_action", "critical")
TRIGGER_TYPES = ("manual", "interval", "once", "event")
ACTION_KINDS = ("prompt", "workflow")


class AutomationEngine:
    """Persistent IRAS automation engine with fail-closed authority boundaries.

    Trigger persistence and execution state live here. Authority does not: interactive
    executions re-enter ToolRegistry permission checks, while unattended state-changing
    runs require a local authorizer (normally autonomous Master Control on the owner's PC).
    """

    def __init__(self, db: SQLiteDB, bus: EventBus | None = None):
        self.db = db
        self.bus = bus or EventBus()
        self._executor_fn: Callable[[dict[str, Any], dict[str, Any]], Any] | None = None
        self._unattended_authorizer: Callable[[dict[str, Any]], bool] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pool: ThreadPoolExecutor | None = None
        self._unsubscribe = self.bus.subscribe("*", self._on_bus_event)
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS v5_automations(
                automation_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                action_kind TEXT NOT NULL,
                prompt TEXT NOT NULL,
                action_ref TEXT,
                permission_mode TEXT NOT NULL,
                trigger_type TEXT NOT NULL,
                trigger_json TEXT NOT NULL,
                next_run TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                paused INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ready',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_run TEXT,
                last_result TEXT,
                last_error TEXT,
                last_trigger TEXT,
                failure_count INTEGER NOT NULL DEFAULT 0,
                run_token TEXT,
                claim_until TEXT
            )
            """
        )

    @staticmethod
    def _dt(value: str) -> datetime:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    @staticmethod
    def _loads(value: str | None) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _dumps(value: dict[str, Any]) -> str:
        return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def bind_executor(
        self,
        executor: Callable[[dict[str, Any], dict[str, Any]], Any],
        *,
        unattended_authorizer: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        self._executor_fn = executor
        if unattended_authorizer is not None:
            self._unattended_authorizer = unattended_authorizer

    def bind_unattended_authorizer(self, checker: Callable[[dict[str, Any]], bool] | None) -> None:
        self._unattended_authorizer = checker

    def add(
        self,
        *,
        name: str,
        action_kind: str = "prompt",
        prompt: str = "",
        action_ref: str = "",
        permission_mode: str = "read_only",
        trigger_type: str = "manual",
        trigger: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action_kind = str(action_kind or "prompt").strip().lower()
        permission_mode = str(permission_mode or "read_only").strip().lower()
        trigger_type = str(trigger_type or "manual").strip().lower()
        trigger = dict(trigger or {})
        if action_kind not in ACTION_KINDS:
            raise ValueError(f"action_kind must be one of {ACTION_KINDS}")
        if permission_mode not in PERMISSION_MODES:
            raise ValueError(f"permission_mode must be one of {PERMISSION_MODES}")
        if trigger_type not in TRIGGER_TYPES:
            raise ValueError(f"trigger_type must be one of {TRIGGER_TYPES}")
        if action_kind == "prompt" and not str(prompt).strip():
            raise ValueError("Prompt automations require a non-empty prompt.")
        if action_kind == "workflow" and not str(action_ref).strip():
            raise ValueError("Workflow automations require an action_ref workflow id.")

        next_run: str | None = None
        if trigger_type == "interval":
            seconds = int(trigger.get("seconds") or 0)
            if seconds < 60 or seconds > 31536000:
                raise ValueError("Interval automation seconds must be between 60 and 31536000.")
            start_at = str(trigger.get("start_at") or "").strip()
            next_run = self._dt(start_at).isoformat() if start_at else (
                datetime.now(timezone.utc) + timedelta(seconds=seconds)
            ).isoformat()
            trigger["seconds"] = seconds
        elif trigger_type == "once":
            at = str(trigger.get("at") or "").strip()
            if not at:
                raise ValueError("Once automations require trigger.at as an ISO timestamp.")
            next_run = self._dt(at).isoformat()
            trigger["at"] = next_run
        elif trigger_type == "event":
            event = str(trigger.get("event") or "").strip()
            if not event or len(event) > 200:
                raise ValueError("Event automations require trigger.event.")
            trigger["event"] = event
            match = trigger.get("match") or {}
            if not isinstance(match, dict):
                raise ValueError("trigger.match must be an object.")
            trigger["match"] = match

        automation_id = new_id("auto_")
        now = utc_now()
        self.db.execute(
            """INSERT INTO v5_automations(
                automation_id,name,action_kind,prompt,action_ref,permission_mode,
                trigger_type,trigger_json,next_run,enabled,paused,status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,1,0,'ready',?,?)""",
            (
                automation_id,
                str(name or "Automation")[:160],
                action_kind,
                str(prompt or "")[:12000],
                str(action_ref or "")[:160],
                permission_mode,
                trigger_type,
                self._dumps(trigger),
                next_run,
                now,
                now,
            ),
        )
        self.bus.publish(
            "automation.created",
            automation_id=automation_id,
            name=str(name or "Automation")[:160],
            trigger_type=trigger_type,
            permission_mode=permission_mode,
        )
        return self.get(automation_id) or {}

    def get(self, automation_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM v5_automations WHERE automation_id=?",
            (automation_id,),
            fetch="one",
        )
        if not row:
            return None
        row["enabled"] = bool(row.get("enabled"))
        row["paused"] = bool(row.get("paused"))
        row["trigger"] = self._loads(row.get("trigger_json"))
        row.pop("trigger_json", None)
        return row

    def list(self, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT automation_id FROM v5_automations"
        if enabled_only:
            sql += " WHERE enabled=1 AND paused=0"
        sql += " ORDER BY created_at DESC"
        ids = self.db.execute(sql, fetch="all") or []
        rows: list[dict[str, Any]] = []
        for item in ids:
            row = self.get(str(item["automation_id"]))
            if row:
                rows.append(row)
        return rows

    def pause(self, automation_id: str) -> dict[str, Any]:
        self.db.execute(
            "UPDATE v5_automations SET paused=1,status='paused',updated_at=? WHERE automation_id=?",
            (utc_now(), automation_id),
        )
        self.bus.publish("automation.paused", automation_id=automation_id)
        return self.get(automation_id) or {}

    def resume(self, automation_id: str) -> dict[str, Any]:
        row = self.get(automation_id)
        if not row:
            raise KeyError(automation_id)
        next_run = row.get("next_run")
        trigger = row.get("trigger") or {}
        if row.get("trigger_type") == "interval" and not next_run:
            next_run = (
                datetime.now(timezone.utc) + timedelta(seconds=int(trigger.get("seconds") or 60))
            ).isoformat()
        self.db.execute(
            "UPDATE v5_automations SET paused=0,enabled=1,status='ready',next_run=?,updated_at=? WHERE automation_id=?",
            (next_run, utc_now(), automation_id),
        )
        self.bus.publish("automation.resumed", automation_id=automation_id)
        return self.get(automation_id) or {}

    def cancel(self, automation_id: str) -> dict[str, Any]:
        self.db.execute(
            """UPDATE v5_automations
               SET enabled=0,paused=0,status='cancelled',run_token=NULL,claim_until=NULL,updated_at=?
               WHERE automation_id=?""",
            (utc_now(), automation_id),
        )
        self.bus.publish("automation.cancelled", automation_id=automation_id)
        return self.get(automation_id) or {}

    def delete(self, automation_id: str) -> None:
        self.db.execute("DELETE FROM v5_automations WHERE automation_id=?", (automation_id,))
        self.bus.publish("automation.deleted", automation_id=automation_id)

    def required_permission(self, automation_id: str) -> str:
        row = self.get(automation_id)
        if not row:
            raise KeyError(automation_id)
        return str(row.get("permission_mode") or "read_only")

    @staticmethod
    def _matches(expected: dict[str, Any], payload: dict[str, Any]) -> bool:
        return all(payload.get(key) == value for key, value in expected.items())

    def _on_bus_event(self, event) -> None:
        topic = str(getattr(event, "topic", "") or "")
        if not topic or topic.startswith("automation."):
            return
        payload = dict(getattr(event, "payload", {}) or {})
        self.emit_event(topic, payload, interactive=False)

    def emit_event(
        self,
        event: str,
        payload: dict[str, Any] | None = None,
        *,
        interactive: bool = False,
    ) -> list[dict[str, Any]]:
        event = str(event or "").strip()
        payload = dict(payload or {})
        if not event:
            raise ValueError("event is required")
        results: list[dict[str, Any]] = []
        for row in self.list(enabled_only=True):
            if row.get("trigger_type") != "event":
                continue
            trigger = row.get("trigger") or {}
            if str(trigger.get("event") or "") != event:
                continue
            if not self._matches(dict(trigger.get("match") or {}), payload):
                continue
            results.append(
                self._execute(
                    row,
                    source=f"event:{event}",
                    payload={"event": event, **payload},
                    interactive=interactive,
                )
            )
        return results

    def run_now(
        self,
        automation_id: str,
        *,
        payload: dict[str, Any] | None = None,
        interactive: bool = True,
    ) -> dict[str, Any]:
        row = self.get(automation_id)
        if not row:
            raise KeyError(automation_id)
        if not row.get("enabled"):
            raise RuntimeError("Automation is cancelled or disabled.")
        if row.get("paused"):
            raise RuntimeError("Automation is paused.")
        return self._execute(row, source="manual", payload=dict(payload or {}), interactive=interactive)

    def _release_expired_claims(self) -> None:
        self.db.execute(
            """UPDATE v5_automations SET run_token=NULL,claim_until=NULL
               WHERE claim_until IS NOT NULL AND claim_until<?""",
            (utc_now(),),
        )

    def _claim_due(self, *, limit: int = 16, lease_seconds: int = 900) -> list[dict[str, Any]]:
        self._release_expired_claims()
        ids = self.db.execute(
            """SELECT automation_id FROM v5_automations
               WHERE enabled=1 AND paused=0 AND trigger_type IN ('interval','once')
                 AND next_run IS NOT NULL AND next_run<=? AND run_token IS NULL
               ORDER BY next_run LIMIT ?""",
            (utc_now(), max(1, int(limit))),
            fetch="all",
        ) or []
        until = (
            datetime.now(timezone.utc) + timedelta(seconds=max(60, int(lease_seconds)))
        ).isoformat()
        claimed: list[dict[str, Any]] = []
        for item in ids:
            token = new_id("lease_")
            automation_id = str(item["automation_id"])
            self.db.execute(
                """UPDATE v5_automations SET run_token=?,claim_until=?
                   WHERE automation_id=? AND run_token IS NULL""",
                (token, until, automation_id),
            )
            row = self.get(automation_id)
            raw = self.db.execute(
                "SELECT run_token FROM v5_automations WHERE automation_id=?",
                (automation_id,),
                fetch="one",
            ) or {}
            if row and raw.get("run_token") == token:
                row["_lease_token"] = token
                claimed.append(row)
        return claimed

    def _advance_schedule(
        self,
        row: dict[str, Any],
        *,
        waiting_authorization: bool = False,
    ) -> tuple[str | None, int, int]:
        trigger_type = str(row.get("trigger_type") or "")
        trigger = row.get("trigger") or {}
        if trigger_type == "interval":
            seconds = int(trigger.get("seconds") or 60)
            return (
                (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(),
                1,
                0,
            )
        if trigger_type == "once" and waiting_authorization:
            return (row.get("next_run"), 1, 1)
        if trigger_type == "once":
            return (row.get("next_run"), 0, 0)
        return (
            row.get("next_run"),
            int(bool(row.get("enabled"))),
            int(bool(row.get("paused"))),
        )

    def _store_result(
        self,
        row: dict[str, Any],
        *,
        ok: bool,
        result: str,
        status: str,
        source: str,
        waiting_authorization: bool = False,
    ) -> None:
        next_run, enabled, paused = self._advance_schedule(
            row,
            waiting_authorization=waiting_authorization,
        )
        failures = 0 if ok else int(row.get("failure_count") or 0) + 1
        self.db.execute(
            """UPDATE v5_automations
               SET next_run=?,enabled=?,paused=?,status=?,last_run=?,last_result=?,
                   last_error=?,last_trigger=?,failure_count=?,run_token=NULL,claim_until=NULL,updated_at=?
               WHERE automation_id=?""",
            (
                next_run,
                enabled,
                paused,
                status,
                utc_now(),
                result[:16000],
                "" if ok else result[:4000],
                source[:240],
                failures,
                utc_now(),
                row["automation_id"],
            ),
        )

    def _execute(
        self,
        row: dict[str, Any],
        *,
        source: str,
        payload: dict[str, Any],
        interactive: bool,
    ) -> dict[str, Any]:
        automation_id = str(row["automation_id"])
        permission = str(row.get("permission_mode") or "read_only")
        if not interactive and permission != "read_only":
            allowed = bool(
                self._unattended_authorizer
                and self._unattended_authorizer(dict(row))
            )
            if not allowed:
                message = (
                    "Waiting for owner authorization: unattended state-changing automation "
                    "requires locally armed autonomous Master Control."
                )
                self._store_result(
                    row,
                    ok=False,
                    result=message,
                    status="waiting_authorization",
                    source=source,
                    waiting_authorization=True,
                )
                self.bus.publish(
                    "automation.authorization_required",
                    automation_id=automation_id,
                    permission_mode=permission,
                    source=source,
                )
                return {
                    "automation_id": automation_id,
                    "ok": False,
                    "status": "waiting_authorization",
                    "error": message,
                }

        if self._executor_fn is None:
            raise RuntimeError("Automation executor is not bound.")
        self.db.execute(
            "UPDATE v5_automations SET status='running',updated_at=? WHERE automation_id=?",
            (utc_now(), automation_id),
        )
        self.bus.publish(
            "automation.started",
            automation_id=automation_id,
            source=source,
            permission_mode=permission,
        )
        try:
            output = self._executor_fn(dict(row), dict(payload))
            text = str(output)
            self._store_result(row, ok=True, result=text, status="succeeded", source=source)
            self.bus.publish(
                "automation.finished",
                automation_id=automation_id,
                ok=True,
                source=source,
            )
            return {
                "automation_id": automation_id,
                "ok": True,
                "status": "succeeded",
                "result": output,
            }
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self._store_result(row, ok=False, result=message, status="failed", source=source)
            self.bus.publish(
                "automation.finished",
                automation_id=automation_id,
                ok=False,
                source=source,
                error=message[:1000],
            )
            return {
                "automation_id": automation_id,
                "ok": False,
                "status": "failed",
                "error": message,
            }

    def run_due(self, *, max_claims: int = 16) -> list[dict[str, Any]]:
        return [
            self._execute(
                row,
                source=str(row.get("trigger_type") or "timer"),
                payload={},
                interactive=False,
            )
            for row in self._claim_due(limit=max_claims)
        ]

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, *, poll_seconds: float = 2.0, max_workers: int = 4) -> None:
        if self.running:
            return
        self._stop.clear()
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, min(int(max_workers), 16)),
            thread_name_prefix="iras-v5-automation",
        )

        def loop() -> None:
            while not self._stop.is_set():
                for row in self._claim_due(limit=max_workers):
                    if self._pool:
                        self._pool.submit(
                            self._execute,
                            row,
                            source=str(row.get("trigger_type") or "timer"),
                            payload={},
                            interactive=False,
                        )
                self._stop.wait(max(0.5, float(poll_seconds)))

        self._thread = threading.Thread(
            target=loop,
            name="iras-v5-automation",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=False)
        self._pool = None
'''

VOICE_RUNTIME = r'''from __future__ import annotations

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
'''

STT = r'''from __future__ import annotations

from collections import deque
from pathlib import Path
import os
import queue
import re
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
'''

TEST_FILE = r'''from __future__ import annotations

from datetime import datetime, timezone, timedelta

from iras.v5.automation_engine import AutomationEngine
from iras.v5.common import EventBus, SQLiteDB
from iras.v5.voice_runtime import FullDuplexVoiceRuntime
from iras.voice.stt import Listener


def test_voice_control_phrases_and_wake_state():
    voice = FullDuplexVoiceRuntime(active_window_seconds=30)
    assert voice.detect_wake("IRAS, open Spotify") is True
    assert voice.detect_wake("open Spotify") is False
    assert voice.end_requested("done, that's all") is True
    assert voice.strip_control_phrases("IRAS, open Spotify") == "open Spotify"
    assert voice.strip_control_phrases("open Spotify, done that's all") == "open Spotify"
    status = voice.status()
    assert status["idle_window_seconds"] == 3.0
    assert status["active_window_seconds"] == 30.0


def test_listener_wake_session_extends_and_honors_end_phrase(monkeypatch):
    listener = Listener(seconds=2)
    phrases = iter(["IRAS", "open Spotify", "play Starboy", "done that's all"])
    monkeypatch.setattr(listener, "listen_phrase", lambda **kwargs: next(phrases))
    assert listener.listen_session(idle_seconds=3, active_seconds=30) == "open Spotify play Starboy"


def test_listener_without_wake_is_single_short_command(monkeypatch):
    listener = Listener(seconds=2)
    calls = []
    def fake(**kwargs):
        calls.append(kwargs)
        return "open calculator"
    monkeypatch.setattr(listener, "listen_phrase", fake)
    assert listener.listen_session(idle_seconds=3, active_seconds=30) == "open calculator"
    assert len(calls) == 1
    assert calls[0]["start_timeout"] == 3


def test_automation_manual_event_and_unattended_authority(tmp_path):
    db = SQLiteDB(tmp_path / "state.db")
    bus = EventBus()
    engine = AutomationEngine(db, bus)
    calls = []
    engine.bind_executor(lambda row, payload: calls.append((row["name"], payload)) or "ok")

    manual = engine.add(name="manual", prompt="status", trigger_type="manual")
    result = engine.run_now(manual["automation_id"])
    assert result["ok"] is True
    assert calls[-1][0] == "manual"

    event_job = engine.add(
        name="event",
        prompt="check health",
        trigger_type="event",
        trigger={"event": "monitor.changed", "match": {"healthy": False}},
    )
    assert engine.emit_event("monitor.changed", {"healthy": True}, interactive=False) == []
    fired = engine.emit_event("monitor.changed", {"healthy": False}, interactive=False)
    assert fired and fired[0]["ok"] is True
    assert engine.get(event_job["automation_id"])["status"] == "succeeded"

    due = engine.add(
        name="critical timer",
        prompt="do a state change",
        permission_mode="critical",
        trigger_type="once",
        trigger={"at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()},
    )
    blocked = engine.run_due()
    assert blocked and blocked[0]["status"] == "waiting_authorization"
    state = engine.get(due["automation_id"])
    assert state["paused"] is True
    assert state["status"] == "waiting_authorization"


def test_unattended_state_change_runs_only_with_local_authorizer(tmp_path):
    db = SQLiteDB(tmp_path / "state.db")
    engine = AutomationEngine(db, EventBus())
    engine.bind_executor(lambda row, payload: "changed")
    engine.bind_unattended_authorizer(lambda row: True)
    job = engine.add(
        name="authorized",
        action_kind="prompt",
        prompt="perform authorized work",
        permission_mode="system_action",
        trigger_type="once",
        trigger={"at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()},
    )
    result = engine.run_due()
    assert result[0]["ok"] is True
    assert engine.get(job["automation_id"])["enabled"] is False
'''

DOC_FILE = r'''# IRAS RC6 Candidate — Automation Engine + Wake Voice Session

This update extends the existing v5 operating layer without changing Remote protocol `1`.

## Automation engine

IRAS gains persistent automations with four trigger types: `manual`, `once`, `interval`, and `event`. Actions can be either a natural-language autonomous objective (`prompt`) or a previously recorded verified workflow (`workflow`). Automations have an explicit maximum permission mode: `read_only`, `safe_action`, `system_action`, or `critical`.

Authority remains fail-closed. Read-only automations may run unattended. State-changing unattended automations require autonomous Master Control to be armed locally on the owner PC. If it is not armed, the run moves to `waiting_authorization`; it does not self-elevate. Interactive runs still pass through the normal ToolRegistry, Remote-session, local-policy, emergency-stop, filesystem-root, audit, and Windows/UAC gates.

Model-facing controls are added for listing, creating, running, pausing, resuming, cancelling, deleting, and emitting automation events. Existing recorded workflows can therefore become verified reusable automations.

## Voice behavior

The microphone path now uses a short idle window by default:

- normal listen window: **3 seconds**;
- saying **IRAS** opens a **30-second** command session;
- the session ends immediately on phrases such as **"done that's all"**, **"that's all"**, **"done IRAS"**, or **"end session"**;
- the wake word and end phrase are stripped before the command is dispatched;
- barge-in and the existing full-duplex runtime remain supported.

Environment overrides:

```env
IRAS_WAKE_SESSION=true
IRAS_WAKE_WORDS=iras
IRAS_WAKE_IDLE_SECONDS=3
IRAS_WAKE_ACTIVE_SECONDS=30
IRAS_WAKE_END_PHRASES=done that's all|that's all|done iras|end session
```

Set `IRAS_WAKE_SESSION=false` to restore the previous single long microphone capture behavior.

## Safety invariant

This update does not create an "always trusted" cloud process. Remote protocol remains `1`; a cloud or model request cannot mint its own Windows authority. Unattended state changes must be explicitly armed on the PC, and emergency stop remains authoritative below the automation planner.
'''


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=check)


def backup_file(root: Path, backup: Path, relative: str) -> None:
    src = root / relative
    if src.exists():
        dst = backup / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def replace_once(path: Path, old: str, new: str, *, sentinel: str = "") -> bool:
    text = path.read_text(encoding="utf-8")
    if sentinel and sentinel in text:
        return False
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Patch anchor mismatch in {path}: expected 1 occurrence, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def patch_runtime(root: Path) -> None:
    path = root / "src/iras/v5/runtime.py"
    replace_once(
        path,
        "from .scheduler import PersistentScheduler\n",
        "from .scheduler import PersistentScheduler\nfrom .automation_engine import AutomationEngine\n",
        sentinel="from .automation_engine import AutomationEngine",
    )
    replace_once(
        path,
        "        self.scheduler = PersistentScheduler(self.db, self.bus)\n        self.monitoring = ProactiveMonitor(self.db, self.bus)\n",
        "        self.scheduler = PersistentScheduler(self.db, self.bus)\n        self.automations = AutomationEngine(self.db, self.bus)\n        self.monitoring = ProactiveMonitor(self.db, self.bus)\n",
        sentinel="self.automations = AutomationEngine",
    )
    replace_once(
        path,
        '''    def bind_tool_executor(self, executor: Callable[[str, dict[str, Any]], Any]) -> None:\n        """Bind ToolRegistry.execute so recorded workflows re-enter permission gates."""\n        self._tool_executor = executor\n\n''',
        '''    def bind_tool_executor(self, executor: Callable[[str, dict[str, Any]], Any]) -> None:\n        """Bind ToolRegistry.execute so workflows and automations re-enter permission gates."""\n        self._tool_executor = executor\n        self.automations.bind_executor(self.execute_automation)\n\n    def bind_automation_authorizer(self, checker: Callable[[dict[str, Any]], bool] | None) -> None:\n        self.automations.bind_unattended_authorizer(checker)\n\n''',
        sentinel="def bind_automation_authorizer",
    )
    anchor = '''    def start_research_project(self, question: str) -> dict[str, Any]:\n'''
    method = '''    def execute_automation(self, row: dict[str, Any], trigger_payload: dict[str, Any]) -> Any:\n        action_kind = str(row.get("action_kind") or "prompt").strip().lower()\n        if action_kind == "workflow":\n            workflow_id = str(row.get("action_ref") or "").strip()\n            if not workflow_id:\n                raise ValueError("Automation workflow id is missing.")\n            return self.replay_workflow(workflow_id)\n        if self.orchestration_manager is None:\n            raise RuntimeError("No orchestration manager is attached to automation execution.")\n        prompt = str(row.get("prompt") or "").strip()\n        if not prompt:\n            raise ValueError("Automation prompt is empty.")\n        context = {\n            "automation": True,\n            "automation_id": row.get("automation_id"),\n            "automation_permission": str(row.get("permission_mode") or "read_only"),\n            "automation_trigger": dict(trigger_payload or {}),\n        }\n        run = self.orchestration_manager.submit_objective(\n            prompt,\n            context=context,\n            requester_device="v5-automation",\n        )\n        run_id = str((run or {}).get("run_id") or "")\n        if not run_id:\n            return run\n        try:\n            timeout = int(os.getenv("IRAS_V5_AUTOMATION_WAIT_SECONDS", "1800"))\n        except ValueError:\n            timeout = 1800\n        finished = self.orchestration_manager.wait(run_id, timeout=max(30, min(timeout, 21600)))\n        status = str((finished or {}).get("status") or "").lower()\n        if status in {"failed", "cancelled", "blocked", "interrupted"}:\n            raise RuntimeError(str((finished or {}).get("error") or f"Automation orchestration ended as {status}."))\n        return finished\n\n'''
    replace_once(path, anchor, method + anchor, sentinel="def execute_automation")
    replace_once(
        path,
        '''        self.monitoring.start(poll_seconds=float(os.getenv("IRAS_V5_MONITOR_POLL_SECONDS", "15")))\n        self._started = True\n''',
        '''        if self._tool_executor is not None:\n            self.automations.start(\n                poll_seconds=float(os.getenv("IRAS_V5_AUTOMATION_POLL_SECONDS", "2")),\n                max_workers=int(os.getenv("IRAS_V5_AUTOMATION_WORKERS", "4")),\n            )\n        self.monitoring.start(poll_seconds=float(os.getenv("IRAS_V5_MONITOR_POLL_SECONDS", "15")))\n        self._started = True\n''',
        sentinel="IRAS_V5_AUTOMATION_WORKERS",
    )
    replace_once(
        path,
        '''    def stop_services(self) -> None:\n        self.scheduler.stop()\n        self.monitoring.stop()\n''',
        '''    def stop_services(self) -> None:\n        self.scheduler.stop()\n        self.automations.stop()\n        self.monitoring.stop()\n''',
        sentinel="self.automations.stop()",
    )
    replace_once(
        path,
        '''            "scheduled_jobs": len(self.scheduler.list()),\n            "monitors": len(self.monitoring.list()),\n''',
        '''            "scheduled_jobs": len(self.scheduler.list()),\n            "automations": len(self.automations.list()),\n            "automation_worker_active": self.automations.running,\n            "monitors": len(self.monitoring.list()),\n''',
        sentinel='"automation_worker_active"',
    )


def patch_bootstrap(root: Path) -> None:
    path = root / "src/iras/bootstrap.py"
    replace_once(
        path,
        '''    v5.bind_tool_executor(reg.execute)\n    agent=IRASAgent(provider,reg,memory,audit,s.max_agent_steps,system_prompt=build_system_prompt(s.voice_profile),personality=personality,voice_profile=s.voice_profile,recovery_performance_store=RecoveryRoutePerformanceStore(s.data_dir / 'recovery_route_performance.json'))\n''',
        '''    v5.bind_tool_executor(reg.execute)\n    v5.bind_automation_authorizer(\n        lambda _row: bool(master.status().get("enabled") and master.status().get("autonomous"))\n    )\n    agent=IRASAgent(provider,reg,memory,audit,s.max_agent_steps,system_prompt=build_system_prompt(s.voice_profile),personality=personality,voice_profile=s.voice_profile,recovery_performance_store=RecoveryRoutePerformanceStore(s.data_dir / 'recovery_route_performance.json'))\n''',
        sentinel="bind_automation_authorizer",
    )
    old = '''        master_state = master.status()\n        master_autonomy = bool(master_state.get("enabled") and master_state.get("autonomous"))\n        if master_autonomy:\n            worker_perms = MasterPermissionEngine(\n                PermissionLevel.CRITICAL, None, False, PermissionLevel.CRITICAL, master_control=master\n            )\n        else:\n            worker_perms = PermissionEngine(PermissionLevel.READ, None, True, PermissionLevel.READ)\n        worker_reg = ToolRegistry(worker_perms, audit)\n'''
    new = '''        master_state = master.status()\n        master_autonomy = bool(master_state.get("enabled") and master_state.get("autonomous"))\n        automation_mode = str(context.get("automation_permission") or "").strip().lower()\n        if str(context.get("scheduled_permission") or "").strip().lower() == "read_only":\n            automation_mode = "read_only"\n        automation_caps = {\n            "read_only": PermissionLevel.READ,\n            "safe_action": PermissionLevel.SAFE_ACTION,\n            "system_action": PermissionLevel.SYSTEM_ACTION,\n            "critical": PermissionLevel.CRITICAL,\n        }\n        if automation_mode:\n            worker_cap = automation_caps.get(automation_mode, PermissionLevel.READ)\n            if worker_cap > PermissionLevel.READ and not master_autonomy:\n                raise PermissionError(\n                    "Unattended state-changing automation requires locally armed autonomous Master Control."\n                )\n        else:\n            worker_cap = PermissionLevel.CRITICAL if master_autonomy else PermissionLevel.READ\n        if worker_cap > PermissionLevel.READ and master_autonomy:\n            worker_perms = MasterPermissionEngine(\n                worker_cap, None, False, worker_cap, master_control=master\n            )\n        else:\n            worker_perms = PermissionEngine(PermissionLevel.READ, None, True, PermissionLevel.READ)\n        worker_reg = ToolRegistry(worker_perms, audit)\n'''
    replace_once(path, old, new, sentinel="automation_caps = {")
    replace_once(
        path,
        '''            if master_autonomy\n            else [*FILES, *WEB, *GIT, *API_ACCESS, *memory_tools(memory), *device_bridge_tools(local_device), *v5_tools(v5)]\n''',
        '''            if worker_cap > PermissionLevel.READ\n            else [*FILES, *WEB, *GIT, *API_ACCESS, *memory_tools(memory), *device_bridge_tools(local_device), *v5_tools(v5)]\n''',
        sentinel="if worker_cap > PermissionLevel.READ\n            else",
    )
    replace_once(
        path,
        '''        worker_steps = s.max_agent_steps\n        if master_autonomy:\n            worker_steps = max(worker_steps, int(emergency_execution_limits()["agent_steps"]))\n''',
        '''        worker_steps = s.max_agent_steps\n        if master_autonomy and worker_cap > PermissionLevel.READ:\n            worker_steps = max(worker_steps, int(emergency_execution_limits()["agent_steps"]))\n''',
        sentinel="master_autonomy and worker_cap > PermissionLevel.READ",
    )


def patch_tools(root: Path) -> None:
    path = root / "src/iras/tools/v5.py"
    helper_anchor = '''def make_tools(v5):\n'''
    helpers = '''def _automation_mode_level(mode: str) -> PermissionLevel:\n    return {\n        "read_only": PermissionLevel.READ,\n        "safe_action": PermissionLevel.SAFE_ACTION,\n        "system_action": PermissionLevel.SYSTEM_ACTION,\n        "critical": PermissionLevel.CRITICAL,\n    }.get(str(mode or "read_only").strip().lower(), PermissionLevel.CRITICAL)\n\n\ndef _automation_definition_permission(args: dict[str, Any]) -> PermissionLevel:\n    level = _automation_mode_level(str(args.get("permission_mode") or "read_only"))\n    return PermissionLevel.SAFE_ACTION if level == PermissionLevel.READ else PermissionLevel.CRITICAL\n\n\n'''
    replace_once(path, helper_anchor, helpers + helper_anchor, sentinel="def _automation_mode_level")
    add_anchor = '''    t: list[Tool] = []\n    add = t.append\n\n'''
    add_new = '''    t: list[Tool] = []\n    add = t.append\n\n    def automation_run_permission(args: dict[str, Any]) -> PermissionLevel:\n        automation_id = str(args.get("automation_id") or "")\n        if not automation_id:\n            return PermissionLevel.CRITICAL\n        try:\n            return _automation_mode_level(v5.automations.required_permission(automation_id))\n        except Exception:\n            return PermissionLevel.CRITICAL\n\n'''
    replace_once(path, add_anchor, add_new, sentinel="def automation_run_permission")
    schedule_anchor = '''    add(Tool("v5_schedule_cancel", "Cancel a persistent schedule without deleting its audit record.", _schema({"job_id": _str(100)}, ["job_id"]), lambda job_id: (v5.scheduler.cancel(job_id) or {"cancelled": job_id}), PermissionLevel.SYSTEM_ACTION))\n\n'''
    auto_tools = '''    add(Tool("v5_schedule_cancel", "Cancel a persistent schedule without deleting its audit record.", _schema({"job_id": _str(100)}, ["job_id"]), lambda job_id: (v5.scheduler.cancel(job_id) or {"cancelled": job_id}), PermissionLevel.SYSTEM_ACTION))\n\n    # RC6 automation engine ------------------------------------------------------------------\n    add(Tool("v5_automation_list", "List persistent IRAS automations and their trigger/authority state.", _schema({"enabled_only": {"type": "boolean"}}), lambda enabled_only=False: v5.automations.list(enabled_only=enabled_only), PermissionLevel.READ))\n    add(Tool("v5_automation_get", "Read one persistent IRAS automation.", _schema({"automation_id": _str(100)}, ["automation_id"]), lambda automation_id: v5.automations.get(automation_id), PermissionLevel.READ))\n    add(Tool(\n        "v5_automation_add",\n        "Create a persistent manual/once/interval/event automation. State-changing unattended runs still require locally armed autonomous Master Control.",\n        _schema({\n            "name": {"type": "string", "minLength": 1, "maxLength": 160},\n            "action_kind": {"type": "string", "enum": ["prompt", "workflow"]},\n            "prompt": _str(12000),\n            "action_ref": _str(160),\n            "permission_mode": {"type": "string", "enum": ["read_only", "safe_action", "system_action", "critical"]},\n            "trigger_type": {"type": "string", "enum": ["manual", "interval", "once", "event"]},\n            "trigger": _obj(),\n        }, ["name"]),\n        lambda name, action_kind="prompt", prompt="", action_ref="", permission_mode="read_only", trigger_type="manual", trigger=None: v5.automations.add(\n            name=name, action_kind=action_kind, prompt=prompt, action_ref=action_ref,\n            permission_mode=permission_mode, trigger_type=trigger_type, trigger=trigger or {},\n        ),\n        PermissionLevel.SAFE_ACTION,\n        permission_resolver=_automation_definition_permission,\n    ))\n    add(Tool("v5_automation_run", "Run one automation now through its declared permission cap and normal ToolRegistry gates.", _schema({"automation_id": _str(100), "payload": _obj()}, ["automation_id"]), lambda automation_id, payload=None: v5.automations.run_now(automation_id, payload=payload or {}, interactive=True), PermissionLevel.READ, permission_resolver=automation_run_permission))\n    add(Tool("v5_automation_pause", "Pause one automation.", _schema({"automation_id": _str(100)}, ["automation_id"]), lambda automation_id: v5.automations.pause(automation_id), PermissionLevel.SAFE_ACTION))\n    add(Tool("v5_automation_resume", "Resume one automation.", _schema({"automation_id": _str(100)}, ["automation_id"]), lambda automation_id: v5.automations.resume(automation_id), PermissionLevel.SAFE_ACTION))\n    add(Tool("v5_automation_cancel", "Disable one automation while preserving its execution record.", _schema({"automation_id": _str(100)}, ["automation_id"]), lambda automation_id: v5.automations.cancel(automation_id), PermissionLevel.SYSTEM_ACTION))\n    add(Tool("v5_automation_delete", "Delete one automation definition after critical approval.", _schema({"automation_id": _str(100)}, ["automation_id"]), lambda automation_id: (v5.automations.delete(automation_id) or {"deleted": automation_id}), PermissionLevel.CRITICAL))\n    add(Tool("v5_automation_event", "Emit a named automation event with bounded JSON payload. Matching jobs still enforce their own authority requirements.", _schema({"event": {"type": "string", "minLength": 1, "maxLength": 200}, "payload": _obj()}, ["event"]), lambda event, payload=None: v5.automations.emit_event(event, payload or {}, interactive=True), PermissionLevel.SAFE_ACTION))\n\n'''
    replace_once(path, schedule_anchor, auto_tools, sentinel='"v5_automation_list"')
    status_old = '''def _voice_status(v5):\n    return {\n        "running": bool(v5.voice.running),\n        "speaking": bool(v5.voice.speaking),\n        "wake_words": list(v5.voice.wake_words),\n        "require_wake_word": bool(v5.voice.require_wake_word),\n        "turn_count": len(v5.voice.turns),\n    }\n'''
    status_new = '''def _voice_status(v5):\n    status = v5.voice.status() if hasattr(v5.voice, "status") else {}\n    status.setdefault("running", bool(v5.voice.running))\n    status.setdefault("speaking", bool(v5.voice.speaking))\n    status.setdefault("wake_words", list(v5.voice.wake_words))\n    status.setdefault("require_wake_word", bool(v5.voice.require_wake_word))\n    status.setdefault("turn_count", len(v5.voice.turns))\n    return status\n'''
    replace_once(path, status_old, status_new, sentinel='status = v5.voice.status()')


def write_new_files(root: Path) -> None:
    files = {
        "src/iras/v5/automation_engine.py": AUTOMATION_ENGINE,
        "src/iras/v5/voice_runtime.py": VOICE_RUNTIME,
        "src/iras/voice/stt.py": STT,
        "tests/test_v500_rc6_automation_voice.py": TEST_FILE,
        "docs/V5_0_RC6_AUTOMATION_VOICE.md": DOC_FILE,
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply IRAS RC6 candidate automation + wake voice update")
    parser.add_argument("--repo", default=".", help="IRAS repository root")
    parser.add_argument("--allow-newer", action="store_true", help="allow applying when HEAD is not the validated baseline")
    parser.add_argument("--test", action="store_true", help="run the targeted RC6 pytest after patching")
    args = parser.parse_args()

    root = Path(args.repo).expanduser().resolve()
    required = [root / "src/iras/v5/runtime.py", root / "src/iras/bootstrap.py", root / "src/iras/tools/v5.py"]
    if not all(p.exists() for p in required):
        print(f"ERROR: {root} does not look like the IRAS repository.", file=sys.stderr)
        return 2

    try:
        head = run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    except Exception as exc:
        print(f"ERROR: unable to read git HEAD: {exc}", file=sys.stderr)
        return 2
    if head != EXPECTED_HEAD and not args.allow_newer:
        print(
            f"ERROR: this patch was validated against {EXPECTED_HEAD[:8]}, but repo HEAD is {head[:8]}.\n"
            "Run git pull first, or use --allow-newer only after reviewing the anchors.",
            file=sys.stderr,
        )
        return 3

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = root / ".iras_rc6_backup" / stamp
    for relative in (
        "src/iras/v5/runtime.py",
        "src/iras/bootstrap.py",
        "src/iras/tools/v5.py",
        "src/iras/v5/voice_runtime.py",
        "src/iras/voice/stt.py",
    ):
        backup_file(root, backup, relative)

    try:
        patch_runtime(root)
        patch_bootstrap(root)
        patch_tools(root)
        write_new_files(root)
    except Exception as exc:
        print(f"ERROR: patch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"Backups are in: {backup}", file=sys.stderr)
        return 4

    compile_targets = [
        "src/iras/v5/automation_engine.py",
        "src/iras/v5/runtime.py",
        "src/iras/v5/voice_runtime.py",
        "src/iras/voice/stt.py",
        "src/iras/bootstrap.py",
        "src/iras/tools/v5.py",
        "tests/test_v500_rc6_automation_voice.py",
    ]
    result = run([sys.executable, "-m", "py_compile", *compile_targets], root, check=False)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        print(f"ERROR: syntax validation failed. Backups are in: {backup}", file=sys.stderr)
        return result.returncode or 5

    if args.test:
        result = run([sys.executable, "-m", "pytest", "tests/test_v500_rc6_automation_voice.py", "-q"], root, check=False)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode != 0:
            print(f"ERROR: targeted RC6 tests failed. Backups are in: {backup}", file=sys.stderr)
            return result.returncode

    print("IRAS RC6 candidate update applied successfully.")
    print(f"Backup: {backup}")
    print("Next validation: .\\run-v500-validation.ps1")
    print("Voice defaults: idle=3s, wake 'IRAS' => 30s, end phrase='done that's all'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
