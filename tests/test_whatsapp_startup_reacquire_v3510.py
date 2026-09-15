import pytest

from tests.support.whatsapp_validation_helpers import (
    ensure_app as _ensure_app,
    wait_for_app_ready as _wait_for_app_ready,
)


class FakeExecutor:
    def __init__(self, *, focus_results, foreground_titles, launch=None):
        self.focus_results = list(focus_results)
        self.foreground_titles = list(foreground_titles)
        self.launch_result = launch or {
            "app": "WhatsApp",
            "launch_verified": True,
            "verification": "foreground_window",
        }
        self.launch_calls = 0
        self.focus_calls = 0
        self.observe_calls = 0

    def app_control(self, app, action):
        assert app == "whatsapp"
        assert action == "focus"
        self.focus_calls += 1
        result = self.focus_results.pop(0) if self.focus_results else RuntimeError("missing")
        if isinstance(result, Exception):
            raise result
        return result

    def open_app(self, app):
        assert app == "whatsapp"
        self.launch_calls += 1
        return dict(self.launch_result)

    def computer_observe(self, *, vision, scope, max_elements):
        assert vision == "off"
        assert scope == "foreground"
        self.observe_calls += 1
        title = self.foreground_titles.pop(0) if self.foreground_titles else "WhatsApp"
        return {
            "foreground": {
                "hwnd": 123 if title else 0,
                "title": title,
            }
        }


def test_wait_for_app_ready_survives_transient_missing_window(monkeypatch):
    monkeypatch.setattr("tests.support.whatsapp_validation_helpers.time.sleep", lambda _s: None)
    fake = FakeExecutor(
        focus_results=[
            RuntimeError("not found"),
            RuntimeError("not found"),
            {"verified_state": True},
        ],
        foreground_titles=["Windows PowerShell", "WhatsApp", "WhatsApp"],
    )

    result = _wait_for_app_ready(
        fake,
        timeout=2.0,
        poll_seconds=0.01,
        stable_probes=2,
    )

    assert result["ready"] is True
    assert result["foreground"] == "WhatsApp"
    assert result["stable_probes"] == 2
    assert len(result["reacquire_attempts"]) == 3


def test_ensure_app_launches_then_accepts_stable_foreground_without_immediate_focus(monkeypatch):
    monkeypatch.setattr("tests.support.whatsapp_validation_helpers.time.sleep", lambda _s: None)
    fake = FakeExecutor(
        focus_results=[
            RuntimeError("not running"),  # initial existing-window check
            RuntimeError("handoff"),
            RuntimeError("handoff"),
        ],
        foreground_titles=["WhatsApp", "WhatsApp"],
    )

    result = _ensure_app(fake)

    assert result["mode"] == "launched"
    assert fake.launch_calls == 1
    assert result["ready"]["ready"] is True
    assert result["ready"]["foreground"] == "WhatsApp"


def test_wait_for_app_ready_fails_closed_when_whatsapp_never_becomes_foreground(monkeypatch):
    # Advance monotonic time deterministically so the timeout path is fast.
    ticks = iter([0.0, 0.0, 0.3, 0.6, 0.9, 1.2, 1.5])
    monkeypatch.setattr(
        "tests.support.whatsapp_validation_helpers.time.monotonic",
        lambda: next(ticks, 2.0),
    )
    monkeypatch.setattr("tests.support.whatsapp_validation_helpers.time.sleep", lambda _s: None)
    fake = FakeExecutor(
        focus_results=[RuntimeError("missing")] * 8,
        foreground_titles=["Windows PowerShell"] * 8,
    )

    with pytest.raises(RuntimeError, match="No message was typed or sent"):
        _wait_for_app_ready(fake, timeout=1.0, poll_seconds=0.01, stable_probes=2)
