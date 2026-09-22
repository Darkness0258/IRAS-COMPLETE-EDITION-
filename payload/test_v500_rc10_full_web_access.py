from pathlib import Path
import os
import pytest

from iras.v5.web_access import FullWebAccess, web_action_risk


def test_url_policy_allows_public_http_https_and_blocks_private(tmp_path, monkeypatch):
    web = FullWebAccess(tmp_path)
    monkeypatch.setenv("IRAS_WEB_ALLOW_HTTP", "true")
    monkeypatch.setenv("IRAS_WEB_ALLOW_PRIVATE", "false")
    monkeypatch.setenv("IRAS_WEB_ALLOW_LOCALHOST", "true")

    assert web.validate_url("https://8.8.8.8/").startswith("https://")
    assert web.validate_url("http://8.8.8.8/").startswith("http://")
    assert web.validate_url("localhost:8000/test").startswith("https://")

    with pytest.raises(PermissionError):
        web.validate_url("http://10.0.0.5/admin")
    with pytest.raises(PermissionError):
        web.validate_url("https://192.168.1.2/")
    with pytest.raises(ValueError):
        web.validate_url("file:///etc/passwd")
    with pytest.raises(ValueError):
        web.validate_url("https://user:pass@example.com/")


def test_owner_domain_deny_rule_covers_subdomains(tmp_path, monkeypatch):
    web = FullWebAccess(tmp_path)
    web.set_domain_rule("example.com", "deny")
    monkeypatch.setattr(web, "_host_addresses", lambda host: [])
    with pytest.raises(PermissionError):
        web.validate_url("https://sub.example.com/path")
    assert web.domain_rules()["example.com"] == "deny"
    web.set_domain_rule("example.com", "inherit")
    assert "example.com" not in web.domain_rules()


def test_web_action_risk_escalates_high_impact_clicks_and_submissions():
    assert web_action_risk({"action": "navigate", "url": "https://example.com"}) == "read"
    assert web_action_risk({"action": "fill_label", "label": "Search", "value": "laptops"}) == "system"
    assert web_action_risk({"action": "click_text", "text": "Next"}) == "system"
    assert web_action_risk({"action": "click_text", "text": "Place order"}) == "critical"
    assert web_action_risk({"action": "press", "key": "Enter"}) == "critical"
    assert web_action_risk([{"action": "navigate"}, {"action": "submit"}]) == "critical"


def test_sensitive_credentials_are_not_web_uploadable_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("IRAS_WEB_ALLOW_SENSITIVE_UPLOADS", raising=False)
    assert FullWebAccess._sensitive_upload_path(Path.home() / ".ssh" / "id_rsa")
    assert FullWebAccess._sensitive_upload_path(tmp_path / ".env")
    assert FullWebAccess._sensitive_upload_path(tmp_path / "certificate.pfx")
    assert not FullWebAccess._sensitive_upload_path(tmp_path / "proposal.pdf")


def test_download_filename_is_sanitized():
    assert FullWebAccess._safe_filename("../../evil?.exe") == "evil_.exe"
    assert FullWebAccess._safe_filename("normal report.pdf") == "normal report.pdf"


def test_batch_dispatch_is_bounded_and_submit_receives_authorization(tmp_path, monkeypatch):
    web = FullWebAccess(tmp_path)
    monkeypatch.setattr(web, "search", lambda query, **kw: {"query": query})
    monkeypatch.setattr(web, "snapshot", lambda **kw: {"title": "ok"})
    monkeypatch.setattr(web, "submit", lambda selector, approved, **kw: {"selector": selector, "approved": approved})
    monkeypatch.setattr(web, "status", lambda: {"running": True})

    result = web.batch([
        {"action": "search", "query": "IRAS"},
        {"action": "snapshot"},
        {"action": "submit", "selector": "#confirm"},
    ], approved=True)
    assert result["steps"][0]["result"]["query"] == "IRAS"
    assert result["steps"][2]["result"]["approved"] is True

    with pytest.raises(ValueError):
        web.batch([{"action": "arbitrary_javascript", "source": "alert(1)"}], approved=True)


def test_status_never_claims_unrestricted_authority(tmp_path):
    web = FullWebAccess(tmp_path)
    status = web.status()
    assert "ToolRegistry" in status["authority"]
    assert status["private_network_enabled"] is False
