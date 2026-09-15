from __future__ import annotations

from pathlib import Path

from scripts import validate_v360_clean_tree as clean_tree
from scripts import validate_v360_real_device as real_device


ROOT = Path(__file__).resolve().parents[1]


def test_clean_release_tree_has_no_superseded_or_real_send_validators():
    forbidden = (
        clean_tree.LEGACY_ROOT_DOCS
        | clean_tree.OBSOLETE_ROOT_FILES
        | clean_tree.MOVED_DOC_ROOT_FILES
        | clean_tree.OBSOLETE_RUNNERS
        | clean_tree.DANGEROUS_ONE_OFF_VALIDATORS
    )
    assert not [rel for rel in forbidden if (ROOT / rel).exists()]
    assert not (ROOT / "docs" / "history").exists()


def test_real_device_smoke_path_is_read_only(monkeypatch, capsys):
    calls: list[str] = []

    class FakeExecutor:
        def __init__(self):
            calls.append("init")

        def system_info(self):
            calls.append("system_info")
            return {"platform": "Windows"}

        def computer_status(self):
            calls.append("computer_status")
            return {"available": True}

        def computer_observe(self, *, vision, scope, max_elements):
            calls.append("computer_observe")
            assert vision == "off"
            assert scope == "foreground"
            assert max_elements == 40
            return {
                "observation_id": "release-smoke",
                "foreground": {"title": "PowerShell", "hwnd": 1},
                "uia_available": True,
                "uia_actionable": True,
                "elements": [],
            }

    monkeypatch.setattr(real_device.platform, "system", lambda: "Windows")
    monkeypatch.setattr(real_device.platform, "release", lambda: "test")
    monkeypatch.setattr(real_device, "DeviceExecutor", FakeExecutor)

    real_device.main()

    assert calls == ["init", "system_info", "computer_status", "computer_observe"]
    assert "STATE-CHANGING ACTIONS EXECUTED: False" in capsys.readouterr().out
