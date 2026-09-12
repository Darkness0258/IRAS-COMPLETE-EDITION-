import pytest

from iras.device_bridge.app_catalog import (
    AppCatalog,
    AppEntry,
    ensure_safe_app_request,
)


def sample_entries():
    return [
        AppEntry(
            name="Microsoft Edge",
            target="edge-id",
            kind="app_id",
            source="test",
            process_hint="msedge.exe",
        ),
        AppEntry(
            name="Discord",
            target="discord-id",
            kind="app_id",
            source="test",
            process_hint="Discord.exe",
        ),
        AppEntry(
            name="VLC media player",
            target="vlc-id",
            kind="app_id",
            source="test",
            process_hint="vlc.exe",
        ),
        AppEntry(
            name="WhatsApp",
            target="whatsapp-id",
            kind="app_id",
            source="test",
        ),
    ]


def test_exact_and_alias_app_detection():
    entries = sample_entries()
    assert AppCatalog.best_match("Discord", entries).name == "Discord"
    assert AppCatalog.best_match("edge", entries).name == "Microsoft Edge"
    assert AppCatalog.best_match("VLC", entries).name == "VLC media player"


def test_fuzzy_app_detection():
    entries = sample_entries()
    assert AppCatalog.best_match("whats app", entries).name == "WhatsApp"


def test_shells_and_admin_consoles_remain_blocked():
    for name in (
        "cmd",
        "PowerShell",
        "Windows Terminal",
        "regedit",
        "wsl",
    ):
        with pytest.raises(PermissionError):
            ensure_safe_app_request(name)
