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


def test_clean_tree_allows_ignored_untracked_local_env(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=local-only\n", encoding="utf-8")

    class Result:
        def __init__(self, returncode=0, stdout=""):
            self.returncode = returncode
            self.stdout = stdout

    def fake_git_check(root, *args):
        assert root == tmp_path
        if args[:2] == ("rev-parse", "--is-inside-work-tree"):
            return Result(0, "true\n")
        if args[:2] == ("ls-files", "--error-unmatch"):
            return Result(1, "")
        if args[:2] == ("check-ignore", "-q"):
            return Result(0, "")
        raise AssertionError(args)

    monkeypatch.setattr(clean_tree, "_git_check", fake_git_check)
    assert clean_tree.local_env_release_problem(tmp_path) is None


def test_clean_tree_rejects_tracked_local_env(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=bad-release\n", encoding="utf-8")

    class Result:
        def __init__(self, returncode=0, stdout=""):
            self.returncode = returncode
            self.stdout = stdout

    def fake_git_check(root, *args):
        assert root == tmp_path
        if args[:2] == ("rev-parse", "--is-inside-work-tree"):
            return Result(0, "true\n")
        if args[:2] == ("ls-files", "--error-unmatch"):
            return Result(0, ".env\n")
        raise AssertionError(args)

    monkeypatch.setattr(clean_tree, "_git_check", fake_git_check)
    assert clean_tree.local_env_release_problem(tmp_path) == "local .env is tracked by git"
