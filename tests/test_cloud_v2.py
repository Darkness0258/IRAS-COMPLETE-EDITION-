from pathlib import Path

from iras.remote_client import IRASRemoteClient


def test_remote_client_requires_https_for_remote():
    c = IRASRemoteClient("http://example.com", "x")
    try:
        c.chat("hello")
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("Expected HTTPS guard")


def test_cloud_source_does_not_register_os_tools():
    source = Path("src/iras/cloud_bootstrap.py").read_text(encoding="utf-8")
    assert "tools.shell" not in source
    assert "tools.system" not in source
    assert "tools.filesystem" not in source


def test_openrouter_key_not_present_in_client_sources():
    roots = [Path("clients/web"), Path("clients/android"), Path("src/iras/remote_desktop.py")]
    for root in roots:
        files = [root] if root.is_file() else list(root.rglob("*"))
        for p in files:
            if p.is_file():
                text = p.read_text(encoding="utf-8", errors="ignore")
                assert "OPENROUTER_API_KEY" not in text
