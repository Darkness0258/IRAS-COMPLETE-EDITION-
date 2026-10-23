"""Calendar endpoints. Every one needs the normal IRAS access token.

  GET    /v1/calendar/status
  GET    /v1/calendar/events?days=7
  POST   /v1/calendar/feeds           { url, name?, lead_minutes?, timezone? }
  DELETE /v1/calendar/feeds/{feed_id}
  POST   /v1/calendar/sync

The private link is never sent back to the browser, only its host name.
"""
from __future__ import annotations

import importlib.util
from typing import Any, Callable

from fastapi import Header, HTTPException

from .ical import AgendaError, AgendaUnavailable
from .service import get_service


def _missing() -> str:
    for name in ("icalendar", "recurring_ical_events"):
        if importlib.util.find_spec(name) is None:
            return "Calendar needs the icalendar and recurring-ical-events packages on the server."
    return ""


def register_agenda_routes(app, authorize: Callable[[str | None], Any], get_runtime: Callable[[], Any]) -> None:
    def service():
        return get_service(get_runtime())

    def fail(exc: Exception):
        raise HTTPException(status_code=503 if isinstance(exc, AgendaUnavailable) else 422, detail=str(exc))

    @app.get("/v1/calendar/status")
    def calendar_status(authorization: str | None = Header(default=None)):
        authorize(authorization)
        problem = _missing()
        return {"available": not problem, "reason": problem, "feeds": [] if problem else service().feeds()}

    @app.get("/v1/calendar/events")
    def calendar_events(days: int = 7, authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            events, problems = service().events(max(1, min(31, int(days))))
            return {"events": events, "problems": problems}
        except (AgendaError, AgendaUnavailable) as exc:
            fail(exc)

    @app.post("/v1/calendar/feeds")
    def calendar_add(body: dict, authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            return service().add_feed(body.get("url"), str(body.get("name") or ""), body.get("lead_minutes") or 10, str(body.get("timezone") or ""))
        except (AgendaError, AgendaUnavailable) as exc:
            fail(exc)

    @app.delete("/v1/calendar/feeds/{feed_id}")
    def calendar_remove(feed_id: str, authorization: str | None = Header(default=None)):
        authorize(authorization)
        service().remove_feed(feed_id)
        return {"deleted": feed_id}

    @app.post("/v1/calendar/sync")
    def calendar_sync(authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            return service().sync_all()
        except (AgendaError, AgendaUnavailable) as exc:
            fail(exc)
