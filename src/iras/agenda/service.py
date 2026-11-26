"""Calendars, and a reminder before each event.

Reminders are one-time scheduled jobs whose prompt starts with "[reminder] ",
so they reuse the reminder path: a notice in the browser that she also says out
loud. A repeating job (every 15 minutes) keeps them in step with the calendar:
new events get a reminder, moved events get a new time, removed events lose it.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import threading
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .ical import AgendaError, Event, clean_url, fetch_feed, parse_events, zone

REMINDER_PREFIX = "[reminder] "  # the same marker as iras.v5.reminders


def clean_owner(owner: Any) -> str:
    """A person id, or "" for a calendar that is for everyone. The id goes into a reminder's marker, so it must be plain."""
    owner = str(owner or "").strip()
    if owner and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", owner):
        raise AgendaError("That is not a person id.")
    return owner


def _marker(owner: Any) -> str:
    """The start of a reminder's prompt: for everyone, or for one person (see iras.v5.reminders)."""
    owner = str(owner or "").strip()
    return f"[reminder:{owner}] " if owner else REMINDER_PREFIX
SYNC_PROMPT = "[calendar-sync] keep reminders in step with the calendar"
SYNC_SECONDS = 900
WINDOW_HOURS = 36
CACHE_SECONDS = 300
TOO_CLOSE = timedelta(seconds=45)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _seal(url: str) -> str:
    """The calendar link is a secret. With IRAS_VAULT_MASTER_KEY set it is stored encrypted."""
    key = os.getenv("IRAS_VAULT_MASTER_KEY", "").strip()
    if not key:
        return "plain:" + url
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    sealed = AESGCM(base64.urlsafe_b64decode(key.encode("ascii"))).encrypt(nonce, url.encode("utf-8"), b"iras-agenda")
    return "aesgcm:" + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")


def _open(text: str) -> str:
    kind, _, body = str(text).partition(":")
    if kind == "plain":
        return body
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = os.getenv("IRAS_VAULT_MASTER_KEY", "").strip()
    if not key:
        raise AgendaError("This calendar link is encrypted and IRAS_VAULT_MASTER_KEY is not set.")
    raw = base64.urlsafe_b64decode(body.encode("ascii"))
    return AESGCM(base64.urlsafe_b64decode(key.encode("ascii"))).decrypt(raw[:12], raw[12:], b"iras-agenda").decode("utf-8")


def _sentence(event: Event, minutes: int, tz_name: str) -> str:
    when = ""
    local = zone(tz_name)
    if local is not None:
        when = " (at " + event.start.astimezone(local).strftime("%I:%M %p").lstrip("0") + ")"
    unit = "minute" if minutes == 1 else "minutes"
    return f"{event.title} starts in {minutes} {unit}{when}."[:300]


class AgendaService:
    def __init__(self, db, scheduler, fetch: Callable[[str], bytes] = fetch_feed, now: Callable[[], datetime] | None = None) -> None:
        self.db, self.scheduler, self._fetch = db, scheduler, fetch
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()
        self._cache: dict[str, tuple[float, bytes]] = {}
        db.execute(
            "CREATE TABLE IF NOT EXISTS agenda_feeds (feed_id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, "
            "lead_minutes INTEGER NOT NULL, timezone TEXT NOT NULL, created_at TEXT NOT NULL, last_sync TEXT, last_error TEXT)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS agenda_reminders (key TEXT PRIMARY KEY, feed_id TEXT NOT NULL, uid TEXT NOT NULL, "
            "start_iso TEXT NOT NULL, job_id TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        try:  # "owner" is a person id, or "" for a calendar that is for everyone. Added to a table that may already hold calendars.
            db.execute("ALTER TABLE agenda_feeds ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass  # the column is already there

    # ---------- feeds ----------
    def _rows(self) -> list[dict]:
        return [dict(r) for r in (self.db.execute("SELECT * FROM agenda_feeds ORDER BY created_at", fetch="all") or [])]

    @staticmethod
    def _safe(row: dict) -> dict:
        try:
            host = urllib.parse.urlsplit(_open(row["url"])).hostname or ""
        except Exception:
            host = ""
        return {
            "feed_id": row["feed_id"], "name": row["name"], "host": host, "lead_minutes": int(row["lead_minutes"]),
            "timezone": row["timezone"], "last_sync": row.get("last_sync"), "last_error": row.get("last_error"),
            "owner": row.get("owner") or "",
        }

    def feeds(self) -> list[dict]:
        return [self._safe(r) for r in self._rows()]

    def feed_count(self, owners: tuple[str, ...]) -> int:
        """How many calendars belong to these owners (\"\" is the shared ones). It never opens a calendar link."""
        return sum(1 for row in self._rows() if (row.get("owner") or "") in owners)

    def reminder_job_ids(self) -> set[str]:
        """The scheduled jobs the calendar made for its events (a reminder before each one)."""
        rows = self.db.execute("SELECT job_id FROM agenda_reminders", fetch="all") or []
        return {str(dict(row)["job_id"]) for row in rows}

    def _bytes(self, row: dict, force: bool = False) -> bytes:
        cached = self._cache.get(row["feed_id"])
        if cached and not force and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
        data = self._fetch(_open(row["url"]))
        self._cache[row["feed_id"]] = (time.monotonic(), data)
        return data

    def add_feed(self, url: str, name: str = "", lead_minutes: int = 10, timezone_name: str = "", owner: str = "") -> dict:
        owner = clean_owner(owner)
        url = clean_url(url)
        for row in self._rows():
            if _open(row["url"]) == url:
                raise AgendaError("That calendar is already added.")
        now = self._now()
        data = self._fetch(url)
        events, calendar_tz, calendar_name = parse_events(data, now, now + timedelta(days=7), timezone_name)
        label = " ".join((name or calendar_name or (urllib.parse.urlsplit(url).hostname or "Calendar")).split())[:60]
        feed_id = "cal_" + uuid.uuid4().hex[:10]
        lead = min(120, max(1, int(lead_minutes or 10)))
        with self._lock:
            self.db.execute(
                "INSERT INTO agenda_feeds (feed_id, name, url, lead_minutes, timezone, created_at, owner) VALUES (?,?,?,?,?,?,?)",
                (feed_id, label, _seal(url), lead, timezone_name or "", _iso(now), owner),
            )
            self._cache[feed_id] = (time.monotonic(), data)
            self._ensure_sync_job(now)
            row = next(r for r in self._rows() if r["feed_id"] == feed_id)
            made = self._sync_feed(row)
        return {"feed": self._safe(row), "upcoming": len([e for e in events]), "reminders_set": made}

    def set_owner(self, feed_id: str, owner: str = "") -> dict:
        """Say whose calendar this is ("" for everyone). Its reminders are made again, so they reach the right person."""
        owner = clean_owner(owner)
        with self._lock:
            if next((r for r in self._rows() if r["feed_id"] == feed_id), None) is None:
                raise AgendaError("That calendar is not here.")
            self.db.execute("UPDATE agenda_feeds SET owner=? WHERE feed_id=?", (owner, feed_id))
            for old in self.db.execute("SELECT * FROM agenda_reminders WHERE feed_id=?", (feed_id,), fetch="all") or []:
                self._drop(dict(old))
            row = next(r for r in self._rows() if r["feed_id"] == feed_id)
            try:
                made = self._sync_feed(row)
            except Exception:
                made = 0  # the next sync makes them
        return {"feed": self._safe(row), "reminders_set": made}

    def remove_feed(self, feed_id: str) -> None:
        with self._lock:
            for old in self.db.execute("SELECT key, job_id FROM agenda_reminders WHERE feed_id=?", (feed_id,), fetch="all") or []:
                self._drop(dict(old))
            self.db.execute("DELETE FROM agenda_feeds WHERE feed_id=?", (feed_id,))
            self._cache.pop(feed_id, None)
            if not self._rows():
                for job in self.scheduler.list(enabled_only=True):
                    if job.get("prompt") == SYNC_PROMPT:
                        self.scheduler.cancel(job["job_id"])

    # ---------- what is coming up ----------
    def events(self, days: int = 7, owner: str | None = None) -> tuple[list[dict], list[str]]:
        """Upcoming events. `owner` None: every calendar. "": the shared ones. A person id: that person's."""
        now = self._now()
        out: list[tuple[Event, str, str]] = []
        problems: list[str] = []
        for row in self._rows():
            if owner is not None and (row.get("owner") or "") != owner:
                continue
            try:
                found, _, _ = parse_events(self._bytes(row), now, now + timedelta(days=days), row["timezone"])
                out += [(e, row["name"], row.get("owner") or "") for e in found]
                self.db.execute("UPDATE agenda_feeds SET last_sync=?, last_error=NULL WHERE feed_id=?", (_iso(now), row["feed_id"]))
            except AgendaError as exc:
                problems.append(f"{row['name']}: {exc}")
                self.db.execute("UPDATE agenda_feeds SET last_error=? WHERE feed_id=?", (str(exc)[:200], row["feed_id"]))
        out.sort(key=lambda pair: pair[0].sort_key())
        return [{**e.as_dict(name), "owner": who} for e, name, who in out], problems

    # ---------- reminders ----------
    def _ensure_sync_job(self, now: datetime) -> None:
        for job in self.scheduler.list(enabled_only=True):
            if job.get("prompt") == SYNC_PROMPT:
                return
        self.scheduler.add(name="Calendar sync", prompt=SYNC_PROMPT, interval_seconds=SYNC_SECONDS, next_run=_iso(now + timedelta(seconds=SYNC_SECONDS)))

    def _drop(self, row: dict) -> None:
        try:
            self.scheduler.cancel(row["job_id"])
        except Exception:
            pass  # the job may already be gone
        self.db.execute("DELETE FROM agenda_reminders WHERE key=?", (row["key"],))

    def _sync_feed(self, feed: dict) -> int:
        now = self._now()
        end = now + timedelta(hours=WINDOW_HOURS)
        events, calendar_tz, _ = parse_events(self._bytes(feed, force=True), now, end, feed["timezone"])
        tz_name = feed["timezone"] or calendar_tz
        lead = int(feed["lead_minutes"])
        current: set[str] = set()
        made = 0
        for event in events:
            if event.all_day or event.start <= now:
                continue
            key = hashlib.sha1(f"{feed['feed_id']}|{event.uid}|{_iso(event.start)}".encode()).hexdigest()[:24]
            current.add(key)
            if event.start - now <= TOO_CLOSE:
                continue
            if self.db.execute("SELECT key FROM agenda_reminders WHERE key=?", (key,), fetch="one"):
                continue
            for old in self.db.execute(  # the same event at another time: forget the old reminder
                "SELECT key, job_id FROM agenda_reminders WHERE feed_id=? AND uid=? AND start_iso>?",
                (feed["feed_id"], event.uid, _iso(now)), fetch="all",
            ) or []:
                self._drop(dict(old))
            remind_at = max(event.start - timedelta(minutes=lead), now + timedelta(seconds=5))
            minutes = max(1, round((event.start - remind_at).total_seconds() / 60))
            job = self.scheduler.add(
                name=("Calendar: " + event.title)[:160],
                prompt=_marker(feed.get("owner")) + _sentence(event, minutes, tz_name),
                next_run=_iso(remind_at),
            )
            self.db.execute(
                "INSERT INTO agenda_reminders (key, feed_id, uid, start_iso, job_id, created_at) VALUES (?,?,?,?,?,?)",
                (key, feed["feed_id"], event.uid, _iso(event.start), job["job_id"], _iso(now)),
            )
            made += 1
        for row in self.db.execute("SELECT key, job_id, start_iso FROM agenda_reminders WHERE feed_id=?", (feed["feed_id"],), fetch="all") or []:
            row = dict(row)
            if row["key"] in current:
                continue
            if _iso(now) < row["start_iso"] <= _iso(end):
                self._drop(row)  # the event was removed from the calendar
            elif row["start_iso"] < _iso(now - timedelta(days=1)):
                self.db.execute("DELETE FROM agenda_reminders WHERE key=?", (row["key"],))  # old, tidy up
        return made

    def sync_all(self) -> dict:
        made = errors = 0
        with self._lock:
            rows = self._rows()
            for row in rows:
                try:
                    made += self._sync_feed(row)
                    self.db.execute("UPDATE agenda_feeds SET last_sync=?, last_error=NULL WHERE feed_id=?", (_iso(self._now()), row["feed_id"]))
                except Exception as exc:
                    errors += 1
                    self.db.execute("UPDATE agenda_feeds SET last_error=? WHERE feed_id=?", (str(exc)[:200], row["feed_id"]))
        return {"feeds": len(rows), "reminders_set": made, "errors": errors}


_LOCK = threading.Lock()


def get_service(runtime: Any) -> AgendaService:
    with _LOCK:
        service = getattr(runtime, "_agenda_service", None)
        if service is None:
            service = AgendaService(runtime.db, runtime.scheduler)
            try:
                runtime._agenda_service = service
            except Exception:
                pass
        return service


def handle_scheduled(prompt: str, row: dict, runtime: Any) -> str | None:
    """Called by the scheduler for every due job. Returns None when the job is not ours."""
    if str(prompt or "") != SYNC_PROMPT:
        return None
    return "Calendar synced: " + str(get_service(runtime).sync_all())
