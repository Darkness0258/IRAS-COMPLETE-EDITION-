from __future__ import annotations

import json
from pathlib import Path

import pytest

from iras.master_control import MasterControl, MasterPermissionEngine
from iras.models import ApprovalRequest, PermissionLevel
from iras.security.permissions import PermissionDenied


class FakePolicy:
    def __init__(self):
        self.current = {
            "enabled": True,
            "mode": "control",
            "persistent": True,
            "remaining_seconds": None,
            "allow_power": False,
            "allow_shell": False,
        }
        self.calls = []

    def status(self):
        return dict(self.current)

    def arm(self, mode, *, minutes=60, persistent=False, allow_power=False, allow_shell=False):
        self.calls.append(("arm", mode, minutes, persistent, allow_power, allow_shell))
        self.current.update(
            enabled=True,
            mode=mode,
            persistent=bool(persistent),
            remaining_seconds=None if persistent else int(minutes) * 60,
            allow_power=bool(allow_power),
            allow_shell=bool(allow_shell),
        )
        return self.status()

    def disarm(self, *, kill_switch=False):
        self.calls.append(("disarm", kill_switch))
        self.current.update(enabled=False, mode="off", persistent=False, remaining_seconds=None)
        return self.status()


class FakeStop:
    def __init__(self, tripped=False):
        self.value = tripped

    def tripped(self):
        return self.value

    def assert_clear(self):
        if self.value:
            raise RuntimeError("emergency stop")


def master(tmp_path: Path):
    return MasterControl(
        tmp_path / "master.json",
        remote_policy=FakePolicy(),
        emergency_stop=FakeStop(),
    )


def test_master_enable_arms_full_remote_and_reports_critical(tmp_path):
    m = master(tmp_path)
    state = m.enable(minutes=30, allow_power=True, allow_shell=True, autonomous=True, source="test")
    assert state["enabled"] is True
    assert state["permission_level"] == "CRITICAL"
    assert state["allow_power"] is True
    assert state["allow_shell"] is True
    assert state["autonomous"] is True
    assert state["remote_mode"] == "full"
    assert m.remote_policy.calls[-1][:2] == ("arm", "full")


def test_master_disable_restores_previous_remote_policy(tmp_path):
    m = master(tmp_path)
    m.enable(minutes=30)
    restored = m.disable(source="test")
    assert restored["enabled"] is False
    assert m.remote_policy.current["mode"] == "control"
    assert m.remote_policy.current["persistent"] is True
    assert m.remote_policy.current["allow_shell"] is False
    assert m.remote_policy.current["allow_power"] is False


def test_master_permission_engine_bypasses_prompt_only_while_locally_armed(tmp_path):
    m = master(tmp_path)
    denied = []
    engine = MasterPermissionEngine(
        PermissionLevel.READ,
        lambda req: denied.append(req.tool_name) or False,
        True,
        PermissionLevel.CRITICAL,
        master_control=m,
    )
    req = ApprovalRequest("run_command", PermissionLevel.CRITICAL, {}, "critical")
    with pytest.raises(PermissionDenied):
        engine.authorize(req)
    assert denied == ["run_command"]

    m.enable(minutes=30)
    engine.authorize(req)  # no prompt while Master Control is active
    assert denied == ["run_command"]


def test_master_emergency_stop_disables_elevation(tmp_path):
    policy = FakePolicy()
    stop = FakeStop()
    m = MasterControl(tmp_path / "master.json", remote_policy=policy, emergency_stop=stop)
    m.enable(minutes=30)
    stop.value = True
    status = m.status()
    assert status["enabled"] is False
    assert policy.current["enabled"] is False


def test_master_state_file_contains_no_tokens(tmp_path):
    m = master(tmp_path)
    m.enable(minutes=30)
    text = (tmp_path / "master.json").read_text(encoding="utf-8")
    assert "token" not in text.lower()
    assert "api_key" not in text.lower()


def test_master_surfaces_are_present_in_pc_web_android_and_cloud_client():
    root = Path(__file__).resolve().parents[1]
    cli = (root / "src/iras/cli.py").read_text(encoding="utf-8")
    desktop = (root / "src/iras/desktop.py").read_text(encoding="utf-8")
    cloud_client = (root / "src/iras/cloud_client.py").read_text(encoding="utf-8")
    web = (root / "clients/web/index.html").read_text(encoding="utf-8")
    android = (root / "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java").read_text(encoding="utf-8")

    assert "--master-enable" in cli and "ENABLE MASTER CONTROL" in cli
    assert "Master Control · OFF" in desktop and "_toggle_master" in desktop
    assert "/master on" in cloud_client and "X-IRAS-Remote-Session-ID" in cloud_client
    assert 'id="master"' in web and "Attach Master Session" in web
    assert "masterSessionActive" in android and "X-IRAS-Remote-Session-ID" in android
    assert "master_control.json" in web and "master_control.json" in android


def test_web_and_android_cannot_remotely_enable_local_master():
    root = Path(__file__).resolve().parents[1]
    web = (root / "clients/web/index.html").read_text(encoding="utf-8")
    android = (root / "clients/android/app/src/main/java/com/darkness/iras/MainActivity.java").read_text(encoding="utf-8")
    assert "web/mobile cannot turn it on remotely" in web
    assert "Master Control is OFF on the PC" in android
    assert "/v1/master/enable" not in web
    assert "/v1/master/enable" not in android
