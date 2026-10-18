"""Plain-words help for database connection problems (Supabase and any Postgres).

Used in two places:

1. At server start. ``build_cloud_runtime`` calls :func:`probe_database` once. If the
   database cannot be reached, the server prints a clear explanation and keeps running
   on local storage (or refuses to start when ``IRAS_DATABASE_REQUIRED=true``), instead of
   crashing with a long traceback.

2. By hand, to find the right address:

       python -m iras.memory.db_diagnose                 # checks DATABASE_URL
       python -m iras.memory.db_diagnose --all-regions   # also scans every Supabase region
       python -m iras.memory.db_diagnose --url "postgresql://..."

Passwords are never printed. A wrong region does not receive your password: the Supabase
pooler answers "tenant/user not found" before any password is sent.
"""
from __future__ import annotations

import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlsplit

# Regions Supabase offers. The pooler host is  aws-<0|1>-<region>.pooler.supabase.com
SUPABASE_REGIONS = (
    "us-east-1", "us-east-2", "us-west-1", "us-west-2", "ca-central-1", "sa-east-1",
    "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-central-2", "eu-north-1",
    "ap-south-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "ap-northeast-2",
)
POOLER_HOST = re.compile(r"^(aws-\d+)-([a-z0-9-]+)\.pooler\.supabase\.com$")
DIRECT_HOST = re.compile(r"^db\.([a-z0-9]{20})\.supabase\.co$")

# ---------------------------------------------------------------------------
# What went wrong, in categories
# ---------------------------------------------------------------------------
_CATEGORY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("tenant_not_found", r"tenant/user .{0,160}not found|\(ENOTFOUND\)|tenant or user not found"),
    ("too_many_connections", r"too many (clients|connections)|remaining connection slots|max clients reached|MaxClientsInSessionMode|pool_size"),
    ("auth_failed", r"password authentication failed|authentication failed|SASL|SCRAM|no pg_hba\.conf entry"),
    ("db_missing", r'database ".*" does not exist'),
    ("dns", r"could not translate host name|name or service not known|nodename nor servname|temporary failure in name resolution|getaddrinfo"),
    ("network_unreachable", r"network is unreachable|no route to host|cannot assign requested address"),
    ("refused", r"connection refused|actively refused"),
    ("timeout", r"timeout expired|timed out|connection timeout"),
    ("ssl", r"\bSSL\b|\bTLS\b|certificate"),
)

PLAIN_SUMMARY = {
    "tenant_not_found": "Supabase does not know the project in DATABASE_URL. It is not a password problem.",
    "auth_failed": "The database found the project but refused the password.",
    "dns": "The host name in DATABASE_URL could not be found.",
    "network_unreachable": "This machine cannot reach the database address (often an IPv6-only address).",
    "refused": "The database address is there, but it refused the connection.",
    "timeout": "The database did not answer in time.",
    "ssl": "The secure connection to the database failed.",
    "too_many_connections": "The database has no free connection slots.",
    "db_missing": "The database name at the end of DATABASE_URL does not exist.",
    "missing_driver": "The PostgreSQL driver (psycopg) is not installed.",
    "bad_url": "DATABASE_URL could not be read. It may contain unencoded special characters.",
    "unknown": "The database connection failed for a reason IRAS does not recognise.",
}

# One safe sentence per category for public status pages. No host names, no user names.
PUBLIC_HELP = {
    "tenant_not_found": "Supabase does not recognise the project in DATABASE_URL. Copy the Session pooler string again from Supabase, Connect, and check the project is not paused.",
    "auth_failed": "The database password was refused. Reset it in Supabase and update DATABASE_URL.",
    "dns": "The database host name was not found. Check DATABASE_URL.",
    "network_unreachable": "The database address cannot be reached from this server. Use the Session pooler string.",
    "refused": "The database refused the connection. Check the port in DATABASE_URL.",
    "timeout": "The database did not answer in time. It may be paused or blocked.",
    "ssl": "The secure connection failed. Add ?sslmode=require to DATABASE_URL.",
    "too_many_connections": "The database has no free connection slots. Restart the service.",
    "db_missing": "The database name in DATABASE_URL does not exist.",
    "missing_driver": "Install IRAS with the cloud extra so psycopg is available.",
    "bad_url": "DATABASE_URL could not be read. Encode special characters in the password.",
    "unknown": "The database connection failed. Run python -m iras.memory.db_diagnose.",
}


def classify_error(error: object) -> str:
    text = str(error or "")
    low = text.lower()
    for category, pattern in _CATEGORY_PATTERNS:
        if re.search(pattern, text if category == "tenant_not_found" else low, re.I):
            return category
    return "unknown"


# ---------------------------------------------------------------------------
# Reading and hiding the connection string
# ---------------------------------------------------------------------------
@dataclass
class DatabaseTarget:
    scheme: str = ""
    user: str = ""
    password: str = ""
    host: str = ""
    port: int | None = None
    dbname: str = ""
    query: str = ""
    project_ref: str = ""          # from user "postgres.<ref>" or host "db.<ref>.supabase.co"
    cluster: str = ""              # "aws-0" or "aws-1" for pooler hosts
    region: str = ""               # e.g. ap-southeast-2 for pooler hosts
    is_pooler: bool = False
    is_direct: bool = False
    looks_unencoded: bool = False  # special characters in the password that need % codes
    problems: list[str] = field(default_factory=list)


def parse_database_url(url: str) -> DatabaseTarget:
    t = DatabaseTarget()
    raw = str(url or "").strip()
    if not raw:
        t.problems.append("DATABASE_URL is empty.")
        return t
    # A password with @ # / ? : breaks URL parsing. Detect that before parsing.
    after_scheme = raw.split("://", 1)[-1]
    authority = after_scheme.split("/", 1)[0] if "/" in after_scheme else after_scheme
    if authority.count("@") > 1 or ("#" in raw and "?" not in raw.split("#", 1)[0] and "@" in raw.split("#", 1)[0]):
        t.looks_unencoded = True
    try:
        parts = urlsplit(raw)
        t.scheme = parts.scheme
        t.user = parts.username or ""
        t.password = parts.password or ""
        t.host = (parts.hostname or "").lower()
        t.port = parts.port
        t.dbname = parts.path.lstrip("/")
        t.query = parts.query
    except ValueError:
        t.looks_unencoded = True
        t.problems.append("The connection string could not be read.")
        return t
    if t.scheme not in ("postgresql", "postgres"):
        t.problems.append("It should start with postgresql:// or postgres://")
    if not t.host:
        t.problems.append("There is no host in the connection string.")
    m = POOLER_HOST.match(t.host)
    if m:
        t.is_pooler, t.cluster, t.region = True, m.group(1), m.group(2)
        if "." in t.user:
            t.project_ref = t.user.split(".", 1)[1]
        else:
            t.problems.append('A pooler connection needs the user to be "postgres.<your project ref>", not just "postgres".')
    d = DIRECT_HOST.match(t.host)
    if d:
        t.is_direct, t.project_ref = True, d.group(1)
    return t


def _shorten(value: str) -> str:
    return value if len(value) <= 9 else f"{value[:4]}...{value[-4:]}"


def mask_database_url(url: str) -> str:
    """The connection string with the password hidden and the project name shortened."""
    t = parse_database_url(url)
    if not t.host:
        return "(unreadable connection string)"
    user = t.user
    if "." in user:
        head, ref = user.split(".", 1)
        user = f"{head}.{_shorten(ref)}"
    port = f":{t.port}" if t.port else ""
    q = f"?{t.query}" if t.query else ""
    cred = f"{user}:****@" if t.user else ""
    return f"{t.scheme or 'postgresql'}://{cred}{t.host}{port}/{t.dbname}{q}"


def scrub(text: object, url: str = "") -> str:
    """Remove the password (and any copy of the whole URL) from an error message."""
    out = str(text or "")
    t = parse_database_url(url) if url else None
    for secret in filter(None, [url, getattr(t, "password", "")]):
        out = out.replace(secret, "****")
    return out


# ---------------------------------------------------------------------------
# Plain-words hints
# ---------------------------------------------------------------------------
def hints_for(category: str, target: DatabaseTarget | None = None) -> list[str]:
    t = target or DatabaseTarget()
    used = f" (this one uses {t.cluster}-{t.region})" if t.is_pooler else ""
    if category == "tenant_not_found":
        return [
            "Supabase's pooler answered, but it does not know this project name. A wrong password would say 'password authentication failed' instead.",
            f"Most likely: the host in DATABASE_URL is not the one Supabase shows for your project{used}. Pooler hosts look like aws-0-<region> or aws-1-<region>. Both the number and the region must match your project.",
            "Or: the project is paused. Free Supabase projects pause after about a week without use. Open the dashboard and press Restore project, then wait two minutes.",
            'Or: the part after "postgres." in the user name has a typo, or the project was deleted.',
            "Fix: Supabase, open your project, press Connect, choose Session pooler, and copy the whole string again. Do not edit the host by hand. Put it in DATABASE_URL on Render and redeploy.",
            "To find the right host automatically, run on your PC:  python -m iras.memory.db_diagnose --all-regions",
        ]
    if category == "auth_failed":
        return [
            "The project was found, but the password was refused.",
            "Reset it: Supabase, Project Settings, Database, Reset database password. Use letters and numbers only, or percent-encode symbols (@ becomes %40, # becomes %23, / becomes %2F, : becomes %3A, ? becomes %3F, % becomes %25).",
            "Then copy the connection string again and update DATABASE_URL.",
        ]
    if category == "dns":
        return [
            "The host name could not be found.",
            "Check DATABASE_URL for typos. A host that starts with db. and ends with .supabase.co is the Direct connection. Many hosts, including Render, cannot reach it. Use the Session pooler string instead.",
        ]
    if category == "network_unreachable":
        return [
            "This machine has no route to that address. Supabase's Direct connection (db.<project>.supabase.co) is IPv6 only, and Render cannot reach IPv6.",
            "Use the Session pooler string from Supabase, Connect. It works over IPv4.",
        ]
    if category == "refused":
        return ["The address answered but closed the door. Check the port: Session pooler is 5432, Transaction pooler is 6543."]
    if category == "timeout":
        return [
            "The database did not answer in time.",
            "A paused Supabase project is the usual cause. Open the dashboard and Restore project. Also check that nothing blocks outgoing connections on port 5432.",
        ]
    if category == "ssl":
        return ["Add  ?sslmode=require  to the end of DATABASE_URL."]
    if category == "too_many_connections":
        return [
            "The database has no free connection slots. IRAS keeps one connection for each store (memory, device bridge, skills, v5 state).",
            "Restart the service. If it keeps happening, use the Session pooler on port 5432 and avoid running several copies of the server.",
        ]
    if category == "db_missing":
        return ["The database name at the end of the URL does not exist. On Supabase it is normally  postgres."]
    if category == "missing_driver":
        return ["Install IRAS with the cloud extra:  pip install \"iras-agent[cloud]\""]
    if category == "bad_url":
        return [
            "The connection string could not be read, usually because the password has special characters.",
            "Percent-encode them (@ becomes %40, # becomes %23, / becomes %2F, : becomes %3A, ? becomes %3F, % becomes %25) or reset the password to letters and numbers.",
        ]
    return ["Run  python -m iras.memory.db_diagnose  on your PC for a step by step check."]


# ---------------------------------------------------------------------------
# Trying to connect
# ---------------------------------------------------------------------------
@dataclass
class ProbeResult:
    ok: bool
    category: str = ""
    summary: str = ""
    detail: str = ""
    hints: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    url_masked: str = ""


ConnectFn = Callable[[str, float], None]


def _psycopg_connect(url: str, timeout: float) -> None:
    import psycopg  # imported here so a missing driver is reported clearly

    conn = psycopg.connect(url, connect_timeout=max(1, int(timeout)), autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    finally:
        conn.close()


def probe_database(
    url: str,
    *,
    timeout: float = 8.0,
    attempts: int = 2,
    retry_delay: float = 2.0,
    connect: ConnectFn | None = None,
) -> ProbeResult:
    """Try to connect once or twice and say what went wrong in plain words.

    Retries only for problems that can be temporary (timeouts, refused, unreachable).
    A wrong project name or password is never retried.
    """
    target = parse_database_url(url)
    masked = mask_database_url(url)
    run = connect or _psycopg_connect
    started = time.perf_counter()
    category, detail = "unknown", ""
    for attempt in range(max(1, attempts)):
        try:
            run(url, timeout)
            return ProbeResult(True, "ok", "Connected.", "", [], int((time.perf_counter() - started) * 1000), masked)
        except ImportError as exc:
            category, detail = "missing_driver", str(exc)
            break
        except Exception as exc:  # psycopg raises several types; classify by message
            detail = scrub(exc, url)
            category = classify_error(detail)
            if target.looks_unencoded and category in ("unknown", "dns"):
                category = "bad_url"
            if category not in ("timeout", "refused", "network_unreachable", "unknown") or attempt + 1 >= attempts:
                break
            time.sleep(retry_delay)
    hints = hints_for(category, target)
    for problem in target.problems:
        hints.insert(0, problem)
    if target.looks_unencoded and category != "bad_url":
        hints.append("The password in DATABASE_URL seems to contain special characters. Percent-encode them (@ becomes %40, # becomes %23).")
    return ProbeResult(False, category, PLAIN_SUMMARY.get(category, PLAIN_SUMMARY["unknown"]), detail, hints, int((time.perf_counter() - started) * 1000), masked)


def describe_failure(result: ProbeResult) -> list[str]:
    """Log lines for the server console. Safe to print: no password."""
    lines = [f"[IRAS DB] Could not connect to the database: {result.summary}", f"[IRAS DB] Address: {result.url_masked}"]
    lines += [f"[IRAS DB]   {i}. {h}" for i, h in enumerate(result.hints, 1)]
    return lines


def database_required() -> bool:
    return os.getenv("IRAS_DATABASE_REQUIRED", "false").strip().lower() in {"1", "true", "yes", "on"}


def drop_database_url(settings: object) -> None:
    """Make every store fall back to local storage together.

    The memory store, device bridge, skills store and v5 state all read the same
    URL, some from settings and some from the environment. Clear all of them.
    """
    try:
        settings.database_url = ""  # type: ignore[attr-defined]
    except Exception:
        pass
    os.environ["DATABASE_URL"] = ""
    os.environ["IRAS_SKILL_DATABASE_URL"] = ""


# ---------------------------------------------------------------------------
# Finding the right address
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    label: str
    url: str
    host: str
    result: ProbeResult | None = None


def _swap_host(url: str, new_host: str, new_user: str | None = None) -> str:
    out = re.sub(r"@[^/:?#]+", "@" + new_host, url, count=1)
    if new_user:
        out = re.sub(r"://[^:@/]+:", f"://{new_user}:", out, count=1)
    return out


def candidate_urls(url: str, *, all_regions: bool = False) -> list[Candidate]:
    """Other addresses worth trying: the other cluster number, then (optionally) every region."""
    t = parse_database_url(url)
    seen: set[str] = {t.host}
    out: list[Candidate] = []
    user = None
    if t.is_direct and t.project_ref:
        user = f"postgres.{t.project_ref}"
    ref = t.project_ref

    def add(host: str, why: str) -> None:
        if host in seen:
            return
        seen.add(host)
        out.append(Candidate(why, _swap_host(url, host, user), host))

    if t.is_pooler:
        other = "aws-1" if t.cluster == "aws-0" else "aws-0"
        add(f"{other}-{t.region}.pooler.supabase.com", f"same region, {other}")
    elif t.is_direct and ref:
        pass  # the region is unknown, so only the full scan can help
    if all_regions or not t.is_pooler:
        if t.is_pooler or (t.is_direct and ref):
            for cluster in ("aws-1", "aws-0"):
                for region in SUPABASE_REGIONS:
                    add(f"{cluster}-{region}.pooler.supabase.com", f"{cluster}, {region}")
    return out


def scan(url: str, *, all_regions: bool = False, timeout: float = 6.0, workers: int = 6, connect: ConnectFn | None = None) -> list[Candidate]:
    cands = candidate_urls(url, all_regions=all_regions)

    def run(c: Candidate) -> Candidate:
        c.result = probe_database(c.url, timeout=timeout, attempts=1, connect=connect)
        return c

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(run, cands))


def _load_dotenv_quietly() -> None:
    try:
        from iras.config import _load_dotenv  # type: ignore

        _load_dotenv()
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    url = ""
    if "--url" in args:
        url = args[args.index("--url") + 1]
    all_regions = "--all-regions" in args
    reveal = "--reveal" in args
    if "-h" in args or "--help" in args:
        print(__doc__)
        return 0
    _load_dotenv_quietly()
    url = url or os.getenv("DATABASE_URL", "").strip()
    if not url:
        print("DATABASE_URL is not set. Pass it with  --url  or set the environment variable first.")
        return 2

    t = parse_database_url(url)
    print("Checking the database address (the password is never shown)\n")
    print(f"  Address : {mask_database_url(url)}")
    if t.is_pooler:
        print(f"  Type    : Supabase pooler, cluster {t.cluster}, region {t.region}, port {t.port or 5432}")
    elif t.is_direct:
        print("  Type    : Supabase direct connection (IPv6 only, many hosts cannot reach it)")
    print()

    first = probe_database(url, attempts=1)
    if first.ok:
        print(f"  OK. Connected in {first.elapsed_ms} ms. DATABASE_URL works from this computer.")
        print("  If the server on Render still fails, the value on Render is different from this one.")
        return 0
    print(f"  FAILED: {first.summary}")
    for i, h in enumerate(first.hints, 1):
        print(f"   {i}. {h}")

    if first.category in ("tenant_not_found", "dns", "network_unreachable", "timeout") or all_regions:
        cands = candidate_urls(url, all_regions=all_regions)
        if cands:
            print(f"\nLooking for the right host ({len(cands)} to try)...")
            found = [c for c in scan(url, all_regions=all_regions) if c.result and (c.result.ok or c.result.category in ("auth_failed", "db_missing"))]
            if found:
                best = found[0]
                state = "connected" if best.result.ok else f"project found, but: {best.result.summary}"
                print(f"\n  FOUND: {best.host}  ({best.label}) {state}")
                print(f"  Use this address: {mask_database_url(best.url)}")
                if reveal:
                    print(f"\n  Full string (keep it private):\n  {best.url}")
                else:
                    print("  In Supabase, Connect, Session pooler, copy the same string and check that its host matches the one above.")
                    print("  (Run again with --reveal to print the full string with your password.)")
                return 0 if best.result.ok else 1
            print("\n  No Supabase pooler knows this project name.")
            print("  The project is most likely paused or deleted. Open the Supabase dashboard and press Restore project.")
            if not all_regions and t.is_pooler:
                print("  You can also scan every region:  python -m iras.memory.db_diagnose --all-regions")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
