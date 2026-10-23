"""Read a calendar feed (a private .ics link) and list its events.

Works with the "secret address in iCal format" of Google Calendar and with
Outlook, Apple and Nextcloud links. Needs: icalendar, recurring-ical-events.
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

MAX_BYTES = 8 * 1024 * 1024


class AgendaError(ValueError):
    """Something the user can fix (bad link, not a calendar). Safe to show."""


class AgendaUnavailable(RuntimeError):
    """The calendar tools are not installed on this server."""


def _check_host(host: str) -> None:
    """The server must not be tricked into opening addresses inside its own network."""
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise AgendaError("I cannot find that address. Check the link.") from exc
    for info in infos:
        ip = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise AgendaError("That link points inside a private network, so I will not open it.")


def clean_url(url: str) -> str:
    text = str(url or "").strip()
    if text.lower().startswith("webcal://"):
        text = "https://" + text[len("webcal://"):]
    parts = urllib.parse.urlsplit(text)
    if parts.scheme != "https" or not parts.hostname:
        raise AgendaError("The calendar link must start with https:// (or webcal://).")
    _check_host(parts.hostname)
    return text


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        clean_url(newurl)  # a redirect must not lead somewhere private either
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_feed(url: str, timeout: float = 20.0) -> bytes:
    url = clean_url(url)
    opener = urllib.request.build_opener(_SafeRedirect)
    request = urllib.request.Request(url, headers={"User-Agent": "IRAS-calendar/1", "Accept": "text/calendar, */*"})
    try:
        with opener.open(request, timeout=timeout) as response:
            data = response.read(MAX_BYTES + 1)
    except AgendaError:
        raise
    except Exception as exc:  # the message never contains the secret link
        raise AgendaError(f"I could not read that calendar ({type(exc).__name__}).") from exc
    if len(data) > MAX_BYTES:
        raise AgendaError("That calendar file is too large.")
    return data


@dataclass
class Event:
    uid: str
    title: str
    start: Any  # an aware datetime in UTC, or a date for all-day events
    end: Any
    all_day: bool
    location: str

    def as_dict(self, feed: str = "") -> dict:
        return {
            "uid": self.uid,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "all_day": self.all_day,
            "location": self.location,
            "feed": feed,
        }

    def sort_key(self) -> datetime:
        return self.start if isinstance(self.start, datetime) else datetime.combine(self.start, time.min, tzinfo=timezone.utc)


def zone(name: str):
    """A timezone by name, or None when it is empty or unknown."""
    if name:
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(name)
        except Exception:
            return None
    return None


def _utc(value: Any, fallback: str) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=zone(fallback) or timezone.utc)
        return value.astimezone(timezone.utc)
    return value


def parse_events(data: bytes, start: datetime, end: datetime, default_tz: str = "") -> tuple[list[Event], str, str]:
    """Events that overlap [start, end], with repeats worked out. Returns (events, calendar timezone, calendar name)."""
    try:
        import icalendar
        import recurring_ical_events
    except ImportError as exc:
        raise AgendaUnavailable("Calendar needs the icalendar and recurring-ical-events packages on the server.") from exc
    try:
        calendar = icalendar.Calendar.from_ical(data)
    except Exception as exc:
        raise AgendaError("That does not look like a calendar feed.") from exc
    calendar_tz = str(calendar.get("X-WR-TIMEZONE") or "").strip()
    calendar_name = str(calendar.get("X-WR-CALNAME") or "").strip()
    fallback = default_tz or calendar_tz
    events: list[Event] = []
    try:
        found = recurring_ical_events.of(calendar).between(start, end)
    except Exception as exc:
        raise AgendaError("I could not read the events in that calendar.") from exc
    for component in found:
        if str(component.get("STATUS") or "").upper() == "CANCELLED":
            continue
        first = component.start
        last = component.end
        title = str(component.get("SUMMARY") or "(no title)").strip() or "(no title)"
        events.append(
            Event(
                uid=str(component.get("UID") or title),
                title=title,
                start=_utc(first, fallback),
                end=_utc(last, fallback),
                all_day=not isinstance(first, datetime),
                location=str(component.get("LOCATION") or "").strip(),
            )
        )
    events.sort(key=Event.sort_key)
    return events, calendar_tz, calendar_name
