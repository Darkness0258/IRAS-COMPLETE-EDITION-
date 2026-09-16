from __future__ import annotations

import pytest

from iras.device_bridge.store import DeviceBridgeStore


def _store(tmp_path):
    store = DeviceBridgeStore(sqlite_path=tmp_path / "bridge.db")
    store.pair_device(
        device_id="windows-device-12345678",
        display_name="Remote Windows",
        platform="Windows 10",
        device_token="device-secret",
        capabilities=["screen_preview", "ui_click_text", "delete_path"],
        app_version="4.0.0-rc2",
    )
    return store


def test_remote_session_token_is_hashed_bound_and_revocable(tmp_path):
    store = _store(tmp_path)
    session = store.create_remote_session(
        device_id="windows-device-12345678",
        mode="full",
        ttl_seconds=120,
    )
    assert session["session_token"]
    assert session["device_id"] == "windows-device-12345678"
    authorized = store.authorize_remote_session(session["session_id"], session["session_token"])
    assert authorized["device_id"] == "windows-device-12345678"
    assert "token_hash" not in authorized
    assert store.authorize_remote_session(session["session_id"], "wrong") is None
    assert store.revoke_remote_session(session["session_id"])
    assert store.authorize_remote_session(session["session_id"], session["session_token"]) is None
    store.close()


def test_remote_session_permission_classification_fails_before_queue(tmp_path):
    store = _store(tmp_path)
    session = store.create_remote_session(
        device_id="windows-device-12345678",
        mode="read_only",
        ttl_seconds=120,
    )
    auth = store.authorize_remote_session(session["session_id"], session["session_token"])
    with pytest.raises(PermissionError):
        store.remote_request_and_wait(
            session=auth,
            action="ui_click_text",
            arguments={"text": "Settings"},
            timeout=1,
        )
    assert store.recent_commands("windows-device-12345678") == []
    store.close()


def test_remote_session_scopes_are_preserved_for_server_enforcement(tmp_path):
    store = _store(tmp_path)
    session = store.create_remote_session(
        device_id="windows-device-12345678", mode="control", ttl_seconds=120, scopes=["windows"]
    )
    authorized = store.authorize_remote_session(session["session_id"], session["session_token"])
    assert authorized["scopes"] == ["windows"]
    store.close()
