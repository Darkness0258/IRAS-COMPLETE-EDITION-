from pathlib import Path


def test_web_client_keeps_master_and_remote_tokens_session_scoped():
    text = Path("clients/web/index.html").read_text(encoding="utf-8")
    assert 'sessionStorage.setItem("iras-api-token"' in text
    assert 'sessionStorage.setItem("iras-remote-session"' in text
    assert 'token:token.value.trim()' not in text
    assert 'token:c.token||token.value.trim()' not in text


def test_windows_bridge_is_outbound_only_in_setup_contract():
    text = Path("scripts/windows/setup-remote-access.ps1").read_text(encoding="utf-8")
    assert "New-NetFirewallRule" not in text
    assert "Register-ScheduledTask" in text
    assert "https://" in text
