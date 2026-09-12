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


def test_bootstrap_fix_is_now_generic():
    text = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "iras"
        / "device_bridge"
        / "app_catalog.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "early_exit_code" in text
    assert "def _launch_shell_path(" in text
    assert "shell_execute_path" in text
    assert "def _shortcut_discovery(" in text


def test_v31_has_no_app_specific_protocol_mapping():
    text = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "iras"
        / "device_bridge"
        / "app_catalog.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "SAFE_PROTOCOL_FALLBACKS" not in text
    assert "steam://open/main" not in text
    assert "_protocol_for_query" not in text
    assert "_launch_safe_protocol" not in text


def test_shell_names_still_remain_blocked():
    from iras.device_bridge.app_catalog import (
        ensure_safe_app_request,
    )

    import pytest

    for name in (
        "PowerShell",
        "Command Prompt",
        "Windows Terminal",
        "WSL",
        "Registry Editor",
    ):
        with pytest.raises(
            PermissionError
        ):
            ensure_safe_app_request(
                name
            )
