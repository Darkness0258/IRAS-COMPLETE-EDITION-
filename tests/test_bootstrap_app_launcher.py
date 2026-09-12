from __future__ import annotations

from pathlib import Path

import pytest

from iras.device_bridge.app_catalog import (
    AppCatalog,
    AppEntry,
)


class _FakeProcess:
    def __init__(self, code):
        self.pid = 1234
        self._code = code

    def poll(self):
        return self._code


def test_bootstrap_nonzero_exit_is_not_immediate_failure(
    monkeypatch,
    tmp_path,
):
    exe = tmp_path / "Steam.exe"
    exe.write_bytes(b"fake")

    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["cwd"] = kwargs.get("cwd")
        captured["shell"] = kwargs.get("shell")
        return _FakeProcess(4294967295)

    monkeypatch.setattr(
        "iras.device_bridge.app_catalog.subprocess.Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        "iras.device_bridge.app_catalog.time.sleep",
        lambda _seconds: None,
    )

    result = AppCatalog._launch_exe(
        AppEntry(
            name="Steam",
            target=str(exe),
            kind="exe",
            source="app_paths",
            process_hint="Steam.exe",
        )
    )

    assert result["method"] == "direct_exe"
    assert result["early_exit_code"] == 4294967295
    assert captured["cwd"] == str(exe.parent)
    assert captured["shell"] is False


def test_steam_has_explicit_safe_protocol_fallback():
    assert (
        AppCatalog._protocol_for_query("Steam")
        == "steam://open/main"
    )


def test_arbitrary_protocol_name_is_not_allowed():
    assert (
        AppCatalog._protocol_for_query("random-app")
        is None
    )


def test_safe_protocol_launcher_uses_fixed_mapping(
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        "iras.device_bridge.app_catalog.os.startfile",
        lambda value: calls.append(value),
        raising=False,
    )

    result = AppCatalog._launch_safe_protocol(
        "Steam"
    )

    assert calls == [
        "steam://open/main"
    ]
    assert result["method"] == "registered_protocol"


def test_shell_names_still_have_no_protocol_fallback():
    assert (
        AppCatalog._protocol_for_query(
            "PowerShell"
        )
        is None
    )
