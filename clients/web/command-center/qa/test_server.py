"""Test server for browser-test.cjs: the real IRAS server, on a throwaway data folder.

Every route the screens call is the real one. Only three things differ, and only here:
  - the data folder is new and empty (in the temp folder), so your own data is never touched,
    and no database from your .env is used
  - any https calendar link gives back one small fixed calendar, so nothing is downloaded
  - the model setting is a placeholder, because this test never talks to a model
It serves clients/web, like the real server does.

    python clients/web/command-center/qa/test_server.py --port 8765 --token-file /tmp/iras-qa-token

The access token is made new each time and written only to the token file (never printed).
"""
from __future__ import annotations

import argparse
import atexit
import os
import pathlib
import secrets
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[4]


def fixed_calendar() -> bytes:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)

    def stamp(moment: datetime) -> str:
        return moment.strftime("%Y%m%dT%H%M%SZ")

    events = [
        ("qa-dentist", "QA Dentist", now + timedelta(hours=3), "Clinic"),
        ("qa-lunch", "QA Team lunch", now + timedelta(days=1, hours=1), ""),
        ("qa-review", "QA Review", now + timedelta(days=2), "Room 4"),
    ]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//IRAS QA//EN", "X-WR-CALNAME:QA Calendar"]
    for uid, title, start, place in events:
        lines += ["BEGIN:VEVENT", f"UID:{uid}@iras.test", f"DTSTAMP:{stamp(now)}", f"DTSTART:{stamp(start)}",
                  f"DTEND:{stamp(start + timedelta(hours=1))}", f"SUMMARY:{title}"]
        if place:
            lines.append(f"LOCATION:{place}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token-file", required=True, help="where to write the access token for the test")
    args = parser.parse_args()

    scratch = pathlib.Path(tempfile.mkdtemp(prefix="iras-qa-"))
    atexit.register(shutil.rmtree, scratch, True)
    token = secrets.token_hex(16)
    out = pathlib.Path(args.token_file)
    out.write_text(token, encoding="utf-8")
    out.chmod(0o600)

    os.environ.update({
        "IRAS_API_TOKEN": token,
        "IRAS_DATA_DIR": str(scratch / "data"),
        "IRAS_LOG_DIR": str(scratch / "logs"),
        "IRAS_PROVIDER": "openrouter",
        "IRAS_API_KEY": "placeholder-not-a-real-key",
        "IRAS_V5_SCHEDULER_ENABLED": "true",
        "IRAS_CORS_ORIGINS": "*",
        # An empty value stops a database from your .env being used.
        "DATABASE_URL": "",
        "IRAS_SKILL_DATABASE_URL": "",
        "IRAS_DATABASE_REQUIRED": "false",
    })
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "src"))

    import uvicorn

    import iras.agenda.service as agenda
    from iras.cloud_api import app

    def check_link(url: str) -> str:
        text = str(url or "").strip()
        if not text.startswith("https://"):
            raise agenda.AgendaError("The calendar link must start with https:// (or webcal://).")
        return text

    original_init = agenda.AgendaService.__init__

    def init(self, db, scheduler, fetch=None, now=None):  # noqa: ANN001
        original_init(self, db, scheduler, fetch=lambda url: fixed_calendar(), now=now)

    agenda.clean_url = check_link
    agenda.AgendaService.__init__ = init

    print(f"test server ready on http://127.0.0.1:{args.port}  (data folder: {scratch})", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
