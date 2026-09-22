from __future__ import annotations

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
