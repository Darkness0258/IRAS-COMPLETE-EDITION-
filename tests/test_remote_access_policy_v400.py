from __future__ import annotations

import pytest

import iras.remote_access as remote_access
from iras.models import PermissionLevel
from iras.remote_access import RemoteAccessPolicy, action_permission


def _policy(monkeypatch, tmp_path):
    kill = tmp_path / "REMOTE_DISABLED"
    monkeypatch.setattr(remote_access, "KILL_SWITCH_PATH", kill)
    for name in (
        "IRAS_REMOTE_ACCESS_MODE",
        "IRAS_REMOTE_ACCESS_ENABLED",
        "IRAS_REMOTE_ACCESS_PERSISTENT",
        "IRAS_REMOTE_ALLOW_POWER",
        "IRAS_REMOTE_ALLOW_SHELL",
    ):
        monkeypatch.delenv(name, raising=False)
    return RemoteAccessPolicy(tmp_path / "policy.json")


def test_remote_policy_modes_and_high_risk_optins(monkeypatch, tmp_path):
    policy = _policy(monkeypatch, tmp_path)
    with pytest.raises(PermissionError):
        policy.authorize("screen_preview")

    policy.arm("read_only", persistent=True)
    assert policy.authorize("screen_preview") == PermissionLevel.READ
    with pytest.raises(PermissionError):
        policy.authorize("ui_click_text")

    policy.arm("control", persistent=True)
    assert policy.authorize("ui_click_text") == PermissionLevel.SYSTEM_ACTION
    with pytest.raises(PermissionError):
        policy.authorize("delete_path")

    policy.arm("full", persistent=True)
    assert policy.authorize("delete_path") == PermissionLevel.CRITICAL
    with pytest.raises(PermissionError):
        policy.authorize("run_command")
    with pytest.raises(PermissionError):
        policy.authorize("power_action", {"action": "restart"})

    policy.arm("full", persistent=True, allow_power=True, allow_shell=True)
    assert policy.authorize("run_command") == PermissionLevel.CRITICAL
    assert policy.authorize("power_action", {"action": "restart"}) == PermissionLevel.CRITICAL


def test_kill_switch_overrides_environment_and_persisted_arm(monkeypatch, tmp_path):
    policy = _policy(monkeypatch, tmp_path)
    policy.arm("full", persistent=True, allow_power=True, allow_shell=True)
    remote_access.KILL_SWITCH_PATH.write_text("disabled", encoding="utf-8")
    monkeypatch.setenv("IRAS_REMOTE_ACCESS_ENABLED", "true")
    monkeypatch.setenv("IRAS_REMOTE_ACCESS_MODE", "full")
    assert policy.status()["enabled"] is False
    with pytest.raises(PermissionError):
        policy.authorize("delete_path")


def test_action_permission_dynamic_classification():
    assert action_permission("computer_action", {"action": "wait"}) == PermissionLevel.READ
    assert action_permission("computer_action", {"action": "click"}) == PermissionLevel.SYSTEM_ACTION
    assert action_permission("app_control", {"action": "focus"}) == PermissionLevel.SAFE_ACTION
    assert action_permission("app_control", {"action": "close"}) == PermissionLevel.SYSTEM_ACTION
    assert action_permission("power_action", {"action": "lock"}) == PermissionLevel.SAFE_ACTION
    assert action_permission("power_action", {"action": "shutdown"}) == PermissionLevel.CRITICAL
    assert action_permission("unknown_future_action") == PermissionLevel.CRITICAL
