"""A wrong DATABASE_URL must not kill the server, and the error must be understandable.

The first test uses the real message from a failed Render deploy.
"""
from __future__ import annotations

import pytest

from iras.memory import db_diagnose as dd

REAL_ERROR = (
    'connection failed: connection to server at "13.238.183.126", port 5432 failed: '
    "FATAL:  (ENOTFOUND) tenant/user postgres.abcdefghijklmnopqrst not found\n"
    "Multiple connection attempts failed. All failures were:\n"
    "- host: 'aws-0-ap-southeast-2.pooler.supabase.com', port: '5432', hostaddr: '13.237.241.81': "
    "connection failed: connection to server at \"13.237.241.81\", port 5432 failed: "
    "FATAL:  (ENOTFOUND) tenant/user postgres.abcdefghijklmnopqrst not found"
)
SECRET = "S3cret-pw"
URL = f"postgresql://postgres.abcdefghijklmnopqrst:{SECRET}@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres"


def test_real_render_error_is_recognised_as_tenant_not_found():
    assert dd.classify_error(REAL_ERROR) == "tenant_not_found"
    hints = " ".join(dd.hints_for("tenant_not_found", dd.parse_database_url(URL)))
    assert "aws-1" in hints and "paused" in hints and "Session pooler" in hints
    assert "not a password" in dd.PLAIN_SUMMARY["tenant_not_found"].lower() or "password" in hints.lower()


def test_other_errors_are_told_apart():
    assert dd.classify_error('FATAL:  password authentication failed for user "postgres"') == "auth_failed"
    assert dd.classify_error('could not translate host name "db.x.supabase.co" to address') == "dns"
    assert dd.classify_error("connection timeout expired") == "timeout"
    assert dd.classify_error("Network is unreachable") == "network_unreachable"
    assert dd.classify_error("FATAL: MaxClientsInSessionMode: max clients reached") == "too_many_connections"
    assert dd.classify_error("something nobody has seen") == "unknown"


def test_password_is_never_printed():
    masked = dd.mask_database_url(URL)
    assert SECRET not in masked and "****" in masked
    assert "abcdefghijklmnopqrst" not in masked           # the project name is shortened too
    assert "aws-0-ap-southeast-2.pooler.supabase.com" in masked
    assert SECRET not in dd.scrub(f"failed for {URL} with {SECRET}", URL)


def test_parse_reads_cluster_region_and_project():
    t = dd.parse_database_url(URL)
    assert (t.is_pooler, t.cluster, t.region, t.port) == (True, "aws-0", "ap-southeast-2", 5432)
    assert t.project_ref == "abcdefghijklmnopqrst"
    direct = dd.parse_database_url("postgresql://postgres:pw@db.abcdefghijklmnopqrst.supabase.co:5432/postgres")
    assert direct.is_direct and direct.project_ref == "abcdefghijklmnopqrst"
    bare = dd.parse_database_url("postgresql://postgres:pw@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres")
    assert any("postgres.<your project ref>" in p for p in bare.problems)


def test_unencoded_special_characters_are_spotted():
    bad = dd.parse_database_url("postgresql://postgres.abc:p@ss@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres")
    assert bad.looks_unencoded


def test_other_cluster_is_tried_first_and_all_regions_on_request():
    first = dd.candidate_urls(URL)
    assert [c.host for c in first] == ["aws-1-ap-southeast-2.pooler.supabase.com"]
    assert SECRET in first[0].url                          # the password rides along unchanged
    everything = dd.candidate_urls(URL, all_regions=True)
    hosts = {c.host for c in everything}
    assert "aws-1-ap-southeast-1.pooler.supabase.com" in hosts and "aws-0-ap-south-1.pooler.supabase.com" in hosts
    assert "aws-0-ap-southeast-2.pooler.supabase.com" not in hosts   # the one already tried
    assert len(everything) == 2 * len(dd.SUPABASE_REGIONS) - 1


def test_direct_host_scan_switches_to_the_pooler_user_name():
    direct = "postgresql://postgres:pw@db.abcdefghijklmnopqrst.supabase.co:5432/postgres"
    cands = dd.candidate_urls(direct)
    assert cands and all(c.url.startswith("postgresql://postgres.abcdefghijklmnopqrst:pw@aws-") for c in cands)


def test_wrong_project_is_not_retried_but_a_timeout_is():
    calls = {"n": 0}

    def tenant(url, timeout):
        calls["n"] += 1
        raise RuntimeError(REAL_ERROR)

    r = dd.probe_database(URL, attempts=3, retry_delay=0, connect=tenant)
    assert not r.ok and r.category == "tenant_not_found" and calls["n"] == 1
    assert SECRET not in r.detail and "abcdefghijklmnopqrst" not in r.url_masked

    flaky = {"n": 0}

    def sometimes(url, timeout):
        flaky["n"] += 1
        if flaky["n"] == 1:
            raise RuntimeError("connection timeout expired")

    ok = dd.probe_database(URL, attempts=2, retry_delay=0, connect=sometimes)
    assert ok.ok and flaky["n"] == 2


def test_real_driver_reports_a_closed_port_without_a_network():
    r = dd.probe_database("postgresql://u:pw@127.0.0.1:9/db", timeout=2, attempts=1)
    assert not r.ok and r.category in {"refused", "timeout", "network_unreachable"}


def test_server_starts_on_local_storage_when_the_database_is_wrong(monkeypatch, tmp_path):
    from iras import cloud_bootstrap
    from iras.config import Settings

    monkeypatch.chdir(tmp_path)                                  # never read a real .env from the project folder
    monkeypatch.setenv("IRAS_SKILL_DATABASE_URL", "")             # registered here so it is restored afterwards
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("IRAS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("IRAS_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("IRAS_DATABASE_REQUIRED", raising=False)
    monkeypatch.setattr(
        cloud_bootstrap, "probe_database",
        lambda url, **kw: dd.ProbeResult(False, "tenant_not_found", dd.PLAIN_SUMMARY["tenant_not_found"], REAL_ERROR,
                                         dd.hints_for("tenant_not_found"), 12, dd.mask_database_url(url)),
    )
    settings = Settings.load()
    assert settings.database_url == URL

    status = cloud_bootstrap._check_database(settings)

    assert status["mode"] == "sqlite-fallback" and status["ok"] is False and status["category"] == "tenant_not_found"
    assert "Copy the Session pooler string" in status["help"]
    assert settings.database_url == ""                       # every store now falls back together
    import os
    assert os.environ["DATABASE_URL"] == "" and os.environ["IRAS_SKILL_DATABASE_URL"] == ""


def test_server_refuses_to_start_when_the_database_is_required(monkeypatch, tmp_path):
    from iras import cloud_bootstrap
    from iras.config import Settings

    monkeypatch.chdir(tmp_path)                                  # never read a real .env from the project folder
    monkeypatch.setenv("IRAS_SKILL_DATABASE_URL", "")             # registered here so it is restored afterwards
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("IRAS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("IRAS_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("IRAS_DATABASE_REQUIRED", "true")
    monkeypatch.setattr(
        cloud_bootstrap, "probe_database",
        lambda url, **kw: dd.ProbeResult(False, "tenant_not_found", dd.PLAIN_SUMMARY["tenant_not_found"], "", [], 1, "x"),
    )
    with pytest.raises(RuntimeError, match="IRAS_DATABASE_REQUIRED"):
        cloud_bootstrap._check_database(Settings.load())


def test_a_working_database_changes_nothing(monkeypatch, tmp_path):
    from iras import cloud_bootstrap
    from iras.config import Settings

    monkeypatch.chdir(tmp_path)                                  # never read a real .env from the project folder
    monkeypatch.setenv("IRAS_SKILL_DATABASE_URL", "")             # registered here so it is restored afterwards
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("IRAS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("IRAS_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(cloud_bootstrap, "probe_database", lambda url, **kw: dd.ProbeResult(True, "ok", "Connected.", "", [], 5, "x"))
    settings = Settings.load()
    status = cloud_bootstrap._check_database(settings)
    assert status["mode"] == "postgres" and status["ok"] is True and settings.database_url == URL

    monkeypatch.setenv("DATABASE_URL", "")
    assert cloud_bootstrap._check_database(Settings.load())["mode"] == "sqlite-local"


def test_command_line_finds_the_other_cluster_and_hides_the_password(monkeypatch, capsys):
    def fake_probe(url, **kw):
        if "aws-1-ap-southeast-2" in url:
            return dd.ProbeResult(True, "ok", "Connected.", "", [], 40, dd.mask_database_url(url))
        return dd.ProbeResult(False, "tenant_not_found", dd.PLAIN_SUMMARY["tenant_not_found"], REAL_ERROR,
                              dd.hints_for("tenant_not_found", dd.parse_database_url(url)), 30, dd.mask_database_url(url))

    monkeypatch.setattr(dd, "probe_database", fake_probe)
    code = dd.main(["--url", URL])
    out = capsys.readouterr().out
    assert code == 0
    assert "FOUND: aws-1-ap-southeast-2.pooler.supabase.com" in out
    assert SECRET not in out
    code = dd.main(["--url", URL, "--reveal"])
    assert SECRET in capsys.readouterr().out               # only when asked


def test_command_line_says_paused_when_no_region_knows_the_project(monkeypatch, capsys):
    monkeypatch.setattr(
        dd, "probe_database",
        lambda url, **kw: dd.ProbeResult(False, "tenant_not_found", "x", REAL_ERROR, [], 1, dd.mask_database_url(url)),
    )
    code = dd.main(["--url", URL, "--all-regions"])
    out = capsys.readouterr().out
    assert code == 1 and "paused or deleted" in out and SECRET not in out
