"""The list of PC actions and the server's limit, which the web "PC" screen shows.

The list is plain data built from the same sets that action_permission() uses, so the
screen can never promise a level the server will not give.
"""
import types

import pytest

from iras.models import PermissionLevel
from iras.remote_access import (
    CRITICAL_ACTIONS,
    READ_ACTIONS,
    SAFE_ACTIONS,
    SYSTEM_ACTIONS,
    VARIES_WITH_ARGUMENTS,
    action_catalog,
    action_permission,
    remote_policy_summary,
)


def test_every_action_in_the_list_has_the_level_the_server_would_give_it():
    rows = action_catalog()
    assert rows
    for row in rows:
        assert action_permission(row["name"], {}).name == row["level"], row


def test_each_action_is_listed_once_in_order():
    names = [row["name"] for row in action_catalog()]
    assert names == sorted(set(names))
    for group in (READ_ACTIONS, SAFE_ACTIONS, SYSTEM_ACTIONS, CRITICAL_ACTIONS):
        assert group <= set(names)


def test_the_screen_and_reading_actions_need_only_look_only():
    levels = {row["name"]: row["level"] for row in action_catalog()}
    for name in ("system_info", "screen_preview", "read_text", "list_directory"):
        assert levels[name] == "READ"


def test_actions_that_change_things_need_more():
    levels = {row["name"]: row["level"] for row in action_catalog()}
    assert levels["write_text"] == "SYSTEM_ACTION"
    assert levels["open_app"] == "SAFE_ACTION"
    for name in ("run_command", "delete_path", "kill_process", "software_install"):
        assert levels[name] == "CRITICAL"


def test_actions_that_depend_on_their_arguments_are_marked():
    marked = {row["name"] for row in action_catalog() if row["varies"]}
    assert marked == VARIES_WITH_ARGUMENTS == {"computer_action", "app_control", "power_action"}
    assert action_permission("power_action", {"action": "lock"}) == PermissionLevel.SAFE_ACTION
    assert action_permission("power_action", {"action": "shutdown"}) == PermissionLevel.CRITICAL


def test_a_made_up_action_is_critical():
    assert action_permission("made_up_action", {}) == PermissionLevel.CRITICAL  # unknown commands fail closed


@pytest.mark.parametrize(
    "cap,allowed",
    [
        (0, {"read_only": True, "control": False, "full": False}),
        (2, {"read_only": True, "control": True, "full": False}),  # the server's default
        (3, {"read_only": True, "control": True, "full": True}),
        (9, {"read_only": True, "control": True, "full": True}),  # too high is cut to the top
        (-4, {"read_only": True, "control": False, "full": False}),  # too low is cut to the bottom
    ],
)
def test_modes_follow_the_servers_limit(cap, allowed):
    assert remote_policy_summary(cap)["modes"] == allowed


def test_the_summary_names_the_limit_and_carries_the_list():
    summary = remote_policy_summary(2)
    assert summary["cap"] == "SYSTEM_ACTION"
    assert summary["actions"] == action_catalog()


def test_the_policy_endpoint_needs_the_token_and_reports_the_servers_limit(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    monkeypatch.chdir(tmp_path)  # importing the server makes data and logs folders
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")  # the server will not start without one AI key
    try:
        from iras import cloud_api as cloud
        from fastapi.testclient import TestClient
    except ImportError as exc:
        pytest.skip(f"the cloud server cannot load in this environment ({exc})")
    monkeypatch.setattr(cloud, "settings", types.SimpleNamespace(api_token="test-token"))
    client = TestClient(cloud.app)
    assert client.get("/v1/remote/policy").status_code == 401
    assert client.get("/v1/remote/policy", headers={"Authorization": "Bearer wrong"}).status_code == 401

    monkeypatch.setenv("IRAS_REMOTE_SESSION_MAX_PERMISSION_LEVEL", "2")
    ok = client.get("/v1/remote/policy", headers={"Authorization": "Bearer test-token"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["cap"] == "SYSTEM_ACTION" and body["modes"]["full"] is False and body["modes"]["control"] is True
    assert body["actions"] == action_catalog()

    monkeypatch.setenv("IRAS_REMOTE_SESSION_MAX_PERMISSION_LEVEL", "3")
    full = client.get("/v1/remote/policy", headers={"Authorization": "Bearer test-token"}).json()
    assert full["cap"] == "CRITICAL" and full["modes"]["full"] is True
