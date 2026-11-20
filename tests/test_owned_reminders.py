"""Reminders and calendars that belong to one person.

A reminder's marker can carry a person id: [reminder:per_abc] text. A calendar that belongs to a
person makes such reminders, and its events say whose they are. Calendars from before this existed
keep working: they are for everyone.
"""
import socket
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_agenda as base  # noqa: E402  (the sample calendar and a fake scheduler)

from iras.agenda import ical, routes  # noqa: E402
from iras.agenda.service import AgendaService, clean_owner  # noqa: E402
from iras.identity.store import IdentityStore  # noqa: E402
from iras.v5 import reminders as rem  # noqa: E402


class DB:
    """Same call style as the project's SQLiteDB: execute(sql, params, fetch=None|"one"|"all")."""

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


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """No real network lookups: every address is a public one."""
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])


NOW = datetime(2026, 10, 24, 10, 10, tzinfo=timezone.utc)
A_URL, B_URL = "https://example.com/a/basic.ics", "https://example.com/b/basic.ics"


def make(db=None):
    db, sched = db or DB(), base.FakeScheduler()
    return AgendaService(db, sched, fetch=lambda url: base.feed(), now=lambda: NOW), sched


def alive(sched):
    """The reminders that are still switched on, with their owner and text."""
    return [(rem.parse(j["prompt"]), j) for j in sched.jobs.values() if j["enabled"] and rem.parse(j["prompt"]) is not None]


# ---------- the marker ----------
@pytest.mark.parametrize("prompt,expected", [
    ("[reminder] call mum", ("", "call mum")),
    ("[Reminder] call mum", ("", "call mum")),
    ("[reminder:per_abc123] call mum", ("per_abc123", "call mum")),
    ("[REMINDER:per-a_1]   spaced out", ("per-a_1", "spaced out")),
    ("[reminder]no space", ("", "no space")),
])
def test_a_reminder_marker_says_who_it_is_for(prompt, expected):
    assert rem.parse(prompt) == expected and rem.is_reminder(prompt)


@pytest.mark.parametrize("prompt", ["hello", "", None, "remind me", "[reminder:bad id] x", "[reminder:] x", "[reminder:" + "a" * 65 + "] x", "x [reminder] y"])
def test_anything_else_is_not_a_reminder(prompt):
    assert rem.parse(prompt) is None and not rem.is_reminder(prompt)


def test_the_marker_can_be_written_and_read_back():
    assert rem.prefix() == rem.PREFIX == "[reminder] "
    assert rem.prefix("per_abc") == "[reminder:per_abc] "
    assert rem.parse(rem.prefix("per_abc") + "hello") == ("per_abc", "hello")


# ---------- delivering ----------
class Notices:
    def __init__(self):
        self.sent = []

    def notify(self, title, text, severity="info", channel="browser"):
        self.sent.append((title, text, severity, channel))


class Phone:
    def __init__(self):
        self.events = []

    def push_event(self, kind, payload):
        self.events.append((kind, payload))


def test_a_reminder_for_everyone_is_delivered_as_before():
    n, m = Notices(), Phone()
    assert rem.deliver("[reminder] Take the bins out", {"job_id": "j1"}, n, m) == "Reminder delivered."
    assert n.sent == [("Reminder", "Take the bins out", "info", "browser")]
    assert m.events == [("reminder.due", {"text": "Take the bins out", "schedule_id": "j1"})]  # no new keys for everyone's reminders


def test_a_reminder_for_a_person_names_them_in_its_title():
    n, m = Notices(), Phone()
    rem.deliver("[reminder:per_a] Call the dentist", {"job_id": "j2"}, n, m, owner_name=lambda pid: {"per_a": "Alice"}.get(pid))
    assert n.sent == [("Reminder for Alice", "Call the dentist", "info", "browser")]
    assert m.events[0][1]["owner"] == "per_a" and m.events[0][1]["for"] == "Alice"


def test_a_reminder_still_arrives_when_the_name_cannot_be_found():
    def broken(pid):
        raise RuntimeError("database is down")

    for finder in (None, lambda pid: None, broken):
        n = Notices()
        rem.deliver("[reminder:per_gone] Call the dentist", {}, n, None, owner_name=finder)
        assert n.sent == [("Reminder for someone", "Call the dentist", "info", "browser")]


def test_delivery_ignores_what_is_not_a_reminder_and_survives_a_bad_phone():
    n = Notices()
    assert rem.deliver("run the weekly report", {}, n) is None and n.sent == []

    class Broken:
        def push_event(self, *a):
            raise OSError("no phone")

    assert rem.deliver("[reminder] hi", {}, n, Broken()) == "Reminder delivered." and len(n.sent) == 1
    n2 = Notices()
    rem.deliver("[reminder] " + "x" * 900, {}, n2)
    assert len(n2.sent[0][1]) == 500
    n3 = Notices()
    rem.deliver("[reminder]", {}, n3)
    assert n3.sent[0][1] == "You asked me to remind you."


# ---------- calendars ----------
@pytest.mark.parametrize("value", ["", None, "per_abc123", "a-b_C9", "x" * 64])
def test_a_good_owner_is_accepted(value):
    assert clean_owner(value) == (value or "")


@pytest.mark.parametrize("value", ["bad id", "a/b", "x" * 65, "per:abc", "../etc", "a\nb"])
def test_a_bad_owner_is_refused(value):
    with pytest.raises(ical.AgendaError, match="person id"):
        clean_owner(value)


def test_a_calendar_that_is_for_everyone_makes_plain_reminders():
    svc, sched = make()
    out = svc.add_feed(A_URL)
    assert out["feed"]["owner"] == ""
    ((owner, text), job), = alive(sched)
    assert owner == "" and text == "Design review starts in 10 minutes (at 3:30 PM)." and job["prompt"].startswith("[reminder] ")


def test_a_calendar_that_belongs_to_a_person_makes_reminders_for_them():
    svc, sched = make()
    out = svc.add_feed(A_URL, owner="per_alice")
    assert out["feed"]["owner"] == "per_alice" and svc.feeds()[0]["owner"] == "per_alice"
    ((owner, text), job), = alive(sched)
    assert owner == "per_alice" and text == "Design review starts in 10 minutes (at 3:30 PM)."
    assert job["prompt"].startswith("[reminder:per_alice] ")
    assert "per_alice" not in str(svc.feeds()[0].get("host", ""))


def test_a_calendar_with_a_bad_owner_is_not_added():
    svc, sched = make()
    with pytest.raises(ical.AgendaError, match="person id"):
        svc.add_feed(A_URL, owner="bad id")
    assert svc.feeds() == [] and alive(sched) == []


def test_events_say_whose_they_are_and_can_be_limited():
    svc, _ = make()
    svc.add_feed(A_URL, name="Shared", owner="")
    svc.add_feed(B_URL, name="Alice", owner="per_alice")
    both, _ = svc.events(7)
    assert Counter(e["owner"] for e in both) == {"": 3, "per_alice": 3}  # the sample calendar holds three events
    mine, _ = svc.events(7, owner="per_alice")
    assert len(mine) == 3 and {e["owner"] for e in mine} == {"per_alice"}
    shared, _ = svc.events(7, owner="")
    assert len(shared) == 3 and {e["owner"] for e in shared} == {""}
    assert svc.events(7, owner="per_bob")[0] == []


def test_changing_whose_calendar_it_is_makes_its_reminders_again():
    svc, sched = make()
    feed_id = svc.add_feed(A_URL)["feed"]["feed_id"]
    out = svc.set_owner(feed_id, "per_alice")
    assert out["feed"]["owner"] == "per_alice" and out["reminders_set"] == 1
    ((owner, _), job), = alive(sched)  # exactly one reminder left on, and it is hers
    assert owner == "per_alice"
    assert sum(1 for j in sched.jobs.values() if rem.is_reminder(j["prompt"]) and not j["enabled"]) == 1  # the old one was switched off
    svc.set_owner(feed_id, "")
    ((owner, _), job), = alive(sched)
    assert owner == "" and job["prompt"].startswith("[reminder] ")
    with pytest.raises(ical.AgendaError, match="not here"):
        svc.set_owner("fd_missing", "per_alice")
    with pytest.raises(ical.AgendaError, match="person id"):
        svc.set_owner(feed_id, "bad id")
    assert svc.feeds()[0]["owner"] == ""  # the refused change changed nothing


def test_a_later_sync_keeps_the_owner_on_new_reminders():
    svc, sched = make()
    svc.add_feed(A_URL, owner="per_alice")
    for j in list(sched.jobs.values()):
        sched.cancel(j["job_id"])
    svc.db.execute("DELETE FROM agenda_reminders")  # as if the reminder had been lost
    svc.sync_all()
    assert alive(sched) and all(owner == "per_alice" for (owner, _), _j in alive(sched))


def test_a_calendar_from_before_owners_existed_still_works():
    fresh = DB()
    make(fresh)  # builds the current tables
    old_sql = fresh.execute("SELECT sql FROM sqlite_master WHERE name='agenda_feeds'", fetch="one")["sql"]
    assert "owner" in old_sql
    before = DB()
    before.execute(old_sql.replace(", owner TEXT NOT NULL DEFAULT ''", ""))  # the table as it was
    before.execute("CREATE TABLE agenda_reminders (key TEXT PRIMARY KEY, feed_id TEXT NOT NULL, uid TEXT NOT NULL, start_iso TEXT NOT NULL, job_id TEXT NOT NULL, created_at TEXT NOT NULL)")
    cols = [r["name"] for r in before.execute("PRAGMA table_info(agenda_feeds)", fetch="all")]
    assert "owner" not in cols
    before.execute("INSERT INTO agenda_feeds (feed_id, name, url, lead_minutes, timezone, created_at) VALUES (?,?,?,?,?,?)", ("fd_old", "My Google calendar", "plain:" + A_URL, 10, "", "2026-10-01T00:00:00+00:00"))
    svc, _ = make(before)  # starting the service adds the column
    assert "owner" in [r["name"] for r in before.execute("PRAGMA table_info(agenda_feeds)", fetch="all")]
    assert svc.feeds()[0]["feed_id"] == "fd_old" and svc.feeds()[0]["owner"] == ""
    make(before)  # starting it again is harmless


# ---------- the server addresses ----------
@pytest.fixture()
def client():
    svc, sched = make()

    class Runtime:
        db, scheduler, _agenda_service = svc.db, sched, svc

    store = IdentityStore(svc.db)
    alice = store.add_person("Alice")["person_id"]
    app = FastAPI()

    def authorize(h):
        if h != "Bearer ok":
            raise HTTPException(status_code=401, detail="no")

    routes.register_agenda_routes(app, authorize, lambda: Runtime)
    c = TestClient(app)
    c.headers.update({"Authorization": "Bearer ok"})
    c.alice, c.sched, c.svc = alice, sched, svc
    return c


def test_a_calendar_can_be_added_for_a_person_she_knows(client):
    r = client.post("/v1/calendar/feeds", json={"url": A_URL, "owner": client.alice})
    assert r.status_code == 200 and r.json()["feed"]["owner"] == client.alice
    ((owner, _), _job), = alive(client.sched)
    assert owner == client.alice
    assert client.get("/v1/calendar/status").json()["feeds"][0]["owner"] == client.alice


def test_a_calendar_for_someone_she_does_not_know_is_refused(client):
    r = client.post("/v1/calendar/feeds", json={"url": A_URL, "owner": "per_nobody"})
    assert r.status_code == 422 and "do not know that person" in r.json()["detail"]
    assert client.post("/v1/calendar/feeds", json={"url": A_URL, "owner": "bad id"}).status_code in (404, 422)
    assert client.svc.feeds() == []


def test_whose_a_calendar_is_can_be_changed_over_the_server(client):
    feed_id = client.post("/v1/calendar/feeds", json={"url": A_URL}).json()["feed"]["feed_id"]
    r = client.post(f"/v1/calendar/feeds/{feed_id}/owner", json={"owner": client.alice})
    assert r.status_code == 200 and r.json()["feed"]["owner"] == client.alice and r.json()["reminders_set"] == 1
    assert client.post(f"/v1/calendar/feeds/{feed_id}/owner", json={"owner": "per_nobody"}).status_code == 422
    assert client.post("/v1/calendar/feeds/fd_missing/owner", json={"owner": ""}).status_code == 422
    assert client.post(f"/v1/calendar/feeds/{feed_id}/owner", json={"owner": ""}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.svc.feeds()[0]["owner"] == client.alice  # the refused ones changed nothing
    assert client.post(f"/v1/calendar/feeds/{feed_id}/owner", json={}).json()["feed"]["owner"] == ""  # no owner means everyone


def test_the_event_list_can_be_limited_by_owner(client):
    client.post("/v1/calendar/feeds", json={"url": A_URL, "name": "Shared"})
    client.post("/v1/calendar/feeds", json={"url": B_URL, "name": "Alice", "owner": client.alice})
    owners = lambda q: Counter(e["owner"] for e in client.get("/v1/calendar/events" + q).json()["events"])  # noqa: E731
    assert owners("") == {"": 3, client.alice: 3}
    assert owners("?owner=") == {"": 3}
    assert owners(f"?owner={client.alice}") == {client.alice: 3}
