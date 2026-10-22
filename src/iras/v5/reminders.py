"""Reminders: a scheduled job whose prompt starts with "[reminder] " is not sent
to an agent. When it is due, her notice goes to the browser and the phone, so the
web screen can show it and say it out loud. The scheduler already makes one-shot
jobs run once and switch themselves off, and it survives restarts.
"""
from __future__ import annotations

from typing import Any

PREFIX = "[reminder] "


def is_reminder(prompt: str) -> bool:
    return str(prompt or "").lower().startswith(PREFIX)


def deliver(prompt: str, row: dict[str, Any], notifications: Any, mobile: Any = None) -> str | None:
    """Send the reminder. Returns None when `prompt` is not a reminder."""
    if not is_reminder(prompt):
        return None
    text = str(prompt)[len(PREFIX):].strip()[:500] or "You asked me to remind you."
    notifications.notify("Reminder", text, severity="info", channel="browser")
    if mobile is not None:
        try:
            mobile.push_event("reminder.due", {"text": text, "schedule_id": (row or {}).get("job_id")})
        except Exception:
            pass  # the browser notice is enough
    return "Reminder delivered."
