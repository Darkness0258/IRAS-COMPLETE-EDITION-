from __future__ import annotations

from pathlib import Path

import pytest

from iras.device_bridge.app_catalog import (
    AppCatalog,
    AppEntry,
    ensure_safe_app_request,
)


class _FakeProcess:
    pid = 4321

    def poll(self):
        return 4294967295


def test_nonzero_bootstrap_exit_is_soft_until_verification(
    monkeypatch,
    tmp_path,
):
    exe = tmp_path / "Example.exe"
    exe.write_bytes(
        b"fake"
    )

    monkeypatch.setattr(
        "iras.device_bridge.app_catalog.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(),
    )
    monkeypatch.setattr(
        "iras.device_bridge.app_catalog.time.sleep",
        lambda _seconds: None,
    )

    result = AppCatalog._launch_exe(
        AppEntry(
            "Example",
            str(exe),
            "exe",
            "app_paths",
            "Example.exe",
        )
    )

    assert (
        result[
            "early_exit_code"
        ]
        == 4294967295
    )


def test_same_app_versions_are_not_ambiguous():
    entries = [
        AppEntry(
            "Blender 5.2",
            "a",
            "app_id",
            "start_apps",
        ),
        AppEntry(
            "Blender 5.2.1.0",
            "b",
            "app_id",
            "start_apps",
        ),
    ]

    best = AppCatalog.best_match(
        "Blender",
        entries,
    )

    assert best.name.startswith(
        "Blender"
    )


def test_shortcut_is_a_supported_launch_kind():
    assert (
        AppCatalog.KIND_PRIORITY[
            "shortcut"
        ]
        > AppCatalog.KIND_PRIORITY[
            "app_id"
        ]
    )


@pytest.mark.parametrize(
    "name",
    [
        "PowerShell",
        "Command Prompt",
        "Windows Terminal",
        "WSL",
        "Registry Editor",
        "Anaconda PowerShell Prompt",
    ],
)
def test_admin_shell_targets_remain_blocked(
    name,
):
    with pytest.raises(
        PermissionError
    ):
        ensure_safe_app_request(
            name
        )
