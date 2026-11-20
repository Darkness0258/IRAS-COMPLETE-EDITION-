"""Reminders: a scheduled job whose prompt starts with a reminder marker is not sent
to an agent. When it is due, her notice goes to the browser and the phone, so the
web screen can show it and say it out loud. The scheduler already makes one-shot
jobs run once and switch themselves off, and it survives restarts.

A reminder can belong to one person. The marker then carries that person's id:

    [reminder] text              for everyone (as before)
    [reminder:per_abc123] text   for one person. A calendar that belongs to a person makes these.

The notice for a person's reminder is titled "Reminder for <name>". The screen shows and
speaks it only to that person, or when nobody is named. For anyone else it says only that a
private reminder is due.
"""
from __future__ import annotations

import re
from typing import Any, Callable

PREFIX = "[reminder] "
_MARK = re.compile(r"^\[reminder(?::([A-Za-z0-9_-]{1,64}))?\][ \t]*", re.IGNORECASE)


def prefix(owner: str = "") -> str:
    """The marker that starts a reminder's prompt."""
    owner = str(owner or "").strip()
    return f"[reminder:{owner}] " if owner else PREFIX


def parse(prompt: str) -> tuple[str, str] | None:
    """(owner, text) for a reminder prompt, or None. The owner is "" for a reminder that is for everyone."""
    text = str(prompt or "")
    found = _MARK.match(text)
    return (found.group(1) or "", text[found.end():].strip()) if found else None


def is_reminder(prompt: str) -> bool:
    return parse(prompt) is not None


def deliver(prompt: str, row: dict[str, Any], notifications: Any, mobile: Any = None, owner_name: Callable[[str], str | None] | None = None) -> str | None:
    """Send the reminder. Returns None when `prompt` is not a reminder.

    `owner_name` turns a person id into the name shown in the title. It may fail or return nothing.
    """
    parsed = parse(prompt)
    if parsed is None:
        return None
    owner, body = parsed
    text = body[:500] or "You asked me to remind you."
    name = ""
    if owner:
        try:
            name = str((owner_name(owner) if owner_name else "") or "").strip()
        except Exception:
            name = ""
    title = ("Reminder for " + (name or "someone")) if owner else "Reminder"
    notifications.notify(title, text, severity="info", channel="browser")
    if mobile is not None:
        payload = {"text": text, "schedule_id": (row or {}).get("job_id")}  # for everyone: exactly as before
        if owner:
            payload.update({"owner": owner, "for": name})
        try:
            mobile.push_event("reminder.due", payload)
        except Exception:
            pass  # the browser notice is enough
    return "Reminder delivered."
