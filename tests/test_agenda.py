import base64
import os
import socket
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

pytest.importorskip("icalendar")
pytest.importorskip("recurring_ical_events")

from iras.agenda import ical, routes  # noqa: E402
from iras.agenda.service import REMINDER_PREFIX, SYNC_PROMPT, AgendaService, _open, _seal, handle_scheduled  # noqa: E402

HEAD = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//test//EN\nX-WR-CALNAME:Work\nX-WR-TIMEZONE:Asia/Karachi\n"
REVIEW = lambda start, end: (  # noqa: E731
    "BEGIN:VEVENT\nUID:review@test\nDTSTAMP:20261020T000000Z\n"
    f"DTSTART:{start}\nDTEND:{end}\nSUMMARY:Design review\nLOCATION:Room 4\nEND:VEVENT\n"
)
OTHERS = """BEGIN:VEVENT
UID:holiday@test
DTSTAMP:20261020T000000Z
DTSTART;VALUE=DATE:20261025
DTEND;VALUE=DATE:20261026
SUMMARY:Holiday
END:VEVENT
BEGIN:VEVENT
UID:weekly@test
DTSTAMP:20261020T000000Z
DTSTART;TZID=Asia/Karachi:20261019T090000
DTEND;TZID=Asia/Karachi:20261019T093000
RRULE:FREQ=WEEKLY;BYDAY=MO,WE
EXDATE;TZID=Asia/Karachi:20261028T090000
SUMMARY:Standup
END:VEVENT
BEGIN:VEVENT
UID:weekly@test
DTSTAMP:20261020T000000Z
RECURRENCE-ID;TZID=Asia/Karachi:20261026T090000
DTSTART;TZID=Asia/Karachi:20261026T110000
DTEND;TZID=Asia/Karachi:20261026T113000
SUMMARY:Standup (moved)
END:VEVENT
BEGIN:VEVENT
UID:cancelled@test
DTSTAMP:20261020T000000Z
DTSTART:20261024T120000Z
DTEND:20261024T130000Z
STATUS:CANCELLED
SUMMARY:Cancelled thing
END:VEVENT
"""


def feed(review="20261024T103000Z", review_end="20261024T113000Z", with_review=True):
    return (HEAD + (REVIEW(review, review_end) if with_review else "") + OTHERS + "END:VCALENDAR\n").encode()


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


class FakeDB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql, params=(), fetch=None):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        if fetch == "one":
            row = cur.fetchone()
            return dict(row) if row else None
        if fetch == "all":
            return [dict(r) for r in cur.fetchall()]
        return None


class FakeScheduler:
    def __init__(self):
        self.jobs = {}
        self.n = 0

    def add(self, *, name, prompt, next_run=None, interval_seconds=None, misfire_policy="skip"):
        self.n += 1
        job = {"job_id": f"j{self.n}", "name": name, "prompt": prompt, "next_run": next_run, "interval_seconds": interval_seconds, "enabled": True}
        self.jobs[job["job_id"]] = job
        return dict(job)

    def list(self, *, enabled_only=False):
        return [dict(j) for j in self.jobs.values() if j["enabled"] or not enabled_only]

    def cancel(self, job_id):
        self.jobs[job_id]["enabled"] = False

    def reminders(self):
        return [j for j in self.jobs.values() if j["enabled"] and j["prompt"].startswith(REMINDER_PREFIX)]


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])


def test_events_with_repeats_exceptions_all_day_and_cancelled():
    events, tz, name = ical.parse_events(feed(), utc(2026, 10, 23), utc(2026, 10, 31))
    titles = [(e.title, e.start.isoformat(), e.all_day) for e in events]
    assert tz == "Asia/Karachi" and name == "Work"
    assert ("Design review", "2026-10-24T10:30:00+00:00", False) in titles
    assert ("Holiday", "2026-10-25", True) in titles
    assert ("Standup (moved)", "2026-10-26T06:00:00+00:00", False) in titles  # 11:00 in Karachi
    assert not any(t[0] == "Cancelled thing" for t in titles)
    assert not any(t[0] == "Standup" and t[1].startswith("2026-10-28") for t in titles)  # the skipped Wednesday
    assert [t[1] for t in titles] == sorted(t[1] for t in titles)


def test_a_non_calendar_file_is_refused_politely():
    with pytest.raises(ical.AgendaError):
        ical.parse_events(b"<html>not a calendar</html>", utc(2026, 10, 23), utc(2026, 10, 31))


@pytest.mark.parametrize("url", ["http://example.com/a.ics", "ftp://example.com/a.ics", "not a link", "https://"])
def test_only_https_links(url):
    with pytest.raises(ical.AgendaError):
        ical.clean_url(url)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.9", "169.254.169.254", "::1"])
def test_private_addresses_are_never_opened(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", (ip, 443))])
    with pytest.raises(ical.AgendaError, match="private"):
        ical.clean_url("https://calendar.example.com/private.ics")


def test_webcal_links_become_https():
    assert ical.clean_url("webcal://example.com/x.ics") == "https://example.com/x.ics"


def make(now, data):
    state = {"data": data, "now": now}
    db, sched = FakeDB(), FakeScheduler()
    svc = AgendaService(db, sched, fetch=lambda url: state["data"], now=lambda: state["now"])
    return svc, sched, state


def test_adding_a_calendar_sets_reminders_and_hides_the_link():
    svc, sched, _ = make(utc(2026, 10, 24, 10, 10), feed())
    out = svc.add_feed("https://example.com/secret-abc/basic.ics")
    assert out["feed"]["name"] == "Work" and out["feed"]["host"] == "example.com"
    assert "secret" not in str(out) and "secret" not in str(svc.feeds())
    (job,) = sched.reminders()
    assert job["next_run"] == "2026-10-24T10:20:00+00:00"  # 10 minutes before 10:30
    assert job["prompt"] == REMINDER_PREFIX + "Design review starts in 10 minutes (at 3:30 PM)."
    assert any(j["prompt"] == SYNC_PROMPT and j["interval_seconds"] == 900 for j in sched.jobs.values())
    with pytest.raises(ical.AgendaError, match="already"):
        svc.add_feed("https://example.com/secret-abc/basic.ics")


def test_sync_is_steady_follows_moves_and_removals():
    svc, sched, state = make(utc(2026, 10, 24, 10, 10), feed())
    svc.add_feed("https://example.com/x.ics")
    assert svc.sync_all()["reminders_set"] == 0 and len(sched.reminders()) == 1  # no duplicates

    state["data"] = feed("20261024T113000Z", "20261024T123000Z")  # moved an hour later
    assert svc.sync_all()["reminders_set"] == 1
    (job,) = sched.reminders()
    assert job["next_run"] == "2026-10-24T11:20:00+00:00"

    state["data"] = feed(with_review=False)  # deleted
    svc.sync_all()
    assert sched.reminders() == []


def test_an_event_already_inside_the_lead_time_reminds_right_away():
    svc, sched, _ = make(utc(2026, 10, 24, 10, 25), feed())
    svc.add_feed("https://example.com/x.ics")
    (job,) = sched.reminders()
    assert job["next_run"] == "2026-10-24T10:25:05+00:00"
    assert "starts in 5 minutes" in job["prompt"]


def test_all_day_and_started_events_get_no_reminder():
    svc, sched, _ = make(utc(2026, 10, 24, 10, 40), feed())  # the review already started
    svc.add_feed("https://example.com/x.ics")
    assert sched.reminders() == []


def test_removing_a_calendar_removes_its_reminders_and_the_sync_job():
    svc, sched, _ = make(utc(2026, 10, 24, 10, 10), feed())
    fid = svc.add_feed("https://example.com/x.ics")["feed"]["feed_id"]
    svc.remove_feed(fid)
    assert sched.reminders() == [] and svc.feeds() == []
    assert not [j for j in sched.jobs.values() if j["enabled"] and j["prompt"] == SYNC_PROMPT]


def test_the_scheduler_hook_only_answers_its_own_job():
    class Runtime:
        pass

    rt = Runtime()
    rt.db, rt.scheduler = FakeDB(), FakeScheduler()
    assert handle_scheduled("Check my email", {}, rt) is None
    assert handle_scheduled(SYNC_PROMPT, {}, rt).startswith("Calendar synced")


def test_the_link_can_be_stored_encrypted(monkeypatch):
    url = "https://example.com/private-token/basic.ics"
    monkeypatch.delenv("IRAS_VAULT_MASTER_KEY", raising=False)
    assert _seal(url).startswith("plain:") and _open(_seal(url)) == url
    pytest.importorskip("cryptography")
    monkeypatch.setenv("IRAS_VAULT_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    sealed = _seal(url)
    assert sealed.startswith("aesgcm:") and "private-token" not in sealed and _open(sealed) == url


def test_endpoints(monkeypatch):
    svc, sched, _ = make(utc(2026, 10, 24, 10, 10), feed())

    class Runtime:
        db, scheduler, _agenda_service = svc.db, sched, svc

    app = FastAPI()

    def authorize(h):
        if h != "Bearer ok":
            raise HTTPException(status_code=401, detail="no")

    routes.register_agenda_routes(app, authorize, lambda: Runtime)
    c = TestClient(app)
    c.headers.update({"Authorization": "Bearer ok"})
    assert TestClient(app).get("/v1/calendar/status").status_code == 401
    assert c.get("/v1/calendar/status").json()["available"] is True
    bad = c.post("/v1/calendar/feeds", json={"url": "http://example.com/x.ics"})
    assert bad.status_code == 422 and "https" in bad.json()["detail"]
    ok = c.post("/v1/calendar/feeds", json={"url": "https://example.com/secret/basic.ics"}).json()
    assert ok["reminders_set"] == 1 and "secret" not in str(ok)
    events = c.get("/v1/calendar/events?days=3").json()["events"]
    assert [e["title"] for e in events][:2] == ["Design review", "Holiday"]
    fid = c.get("/v1/calendar/status").json()["feeds"][0]["feed_id"]
    assert c.delete(f"/v1/calendar/feeds/{fid}").status_code == 200
    assert c.get("/v1/calendar/status").json()["feeds"] == []
