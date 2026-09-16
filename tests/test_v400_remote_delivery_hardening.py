from __future__ import annotations

import json
from pathlib import Path

import iras.remote_desktop as remote_desktop
from iras.device_bridge.store import DeviceBridgeStore
from iras.models import PermissionLevel
from iras.remote_access import RemoteAccessPolicy


def test_web_streaming_chat_carries_remote_session_headers():
    text = Path("clients/web/index.html").read_text(encoding="utf-8")
    start = text.index("async function streamReply")
    end = text.index("async function", start + 20)
    block = text[start:end]
    assert '...remoteHeaders()' in block
    assert '"X-Device-ID":"web"' in block


def test_v4_validation_runner_is_fail_fast_and_rooted():
    text = Path("run-v400-validation.ps1").read_text(encoding="utf-8")
    assert "Set-Location $PSScriptRoot" in text
    assert text.count("if ($LASTEXITCODE -ne 0)") >= 4


def test_remote_task_survives_battery_transition_contract():
    text = Path("scripts/windows/setup-remote-access.ps1").read_text(encoding="utf-8")
    assert "-AllowStartIfOnBatteries" in text
    assert "-DontStopIfGoingOnBatteries" in text
    assert "-MultipleInstances IgnoreNew" in text


def test_remote_desktop_config_protects_master_token(monkeypatch, tmp_path):
    path = tmp_path / "client.json"
    monkeypatch.setattr(remote_desktop, "CONFIG_PATH", path)
    remote_desktop.save_client_config({
        "server_url": "https://example.invalid",
        "token": "master-token-that-should-not-be-plain",
        "hands_free": False,
        "wake_word": "iras",
    })
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "token" not in raw
    assert raw["token_protected"]
    assert "master-token-that-should-not-be-plain" not in path.read_text(encoding="utf-8")
    loaded = remote_desktop.load_client_config()
    assert loaded["token"] == "master-token-that-should-not-be-plain"


def test_full_remote_command_roundtrip_preserves_two_key_gate(monkeypatch, tmp_path):
    # Cloud side: full session authorizes CRITICAL and queues the command bound to
    # exactly one paired device/session. Laptop side: an independent local policy
    # must also explicitly enable command execution.
    store = DeviceBridgeStore(sqlite_path=tmp_path / "bridge.db")
    store.pair_device(
        device_id="windows-e2e-1",
        display_name="E2E Windows",
        platform="Windows 10",
        device_token="device-token",
        capabilities=["run_command"],
        app_version="4.0.0-rc1",
    )
    session = store.create_remote_session(device_id="windows-e2e-1", mode="full", ttl_seconds=120)
    auth = store.authorize_remote_session(session["session_id"], session["session_token"])
    assert auth is not None

    queued = store.enqueue(
        action="run_command",
        arguments={"executable": "python", "args": ["--version"]},
        device_id="windows-e2e-1",
        remote_session_id=session["session_id"],
        permission_level=int(PermissionLevel.CRITICAL),
    )
    claimed = store.claim_next("windows-e2e-1")
    assert claimed["command_id"] == queued["command_id"]
    assert claimed["remote_session_id"] == session["session_id"]
    assert claimed["permission_level"] == int(PermissionLevel.CRITICAL)

    import iras.remote_access as remote_access
    monkeypatch.setattr(remote_access, "KILL_SWITCH_PATH", tmp_path / "REMOTE_DISABLED")
    for name in (
        "IRAS_REMOTE_ACCESS_MODE", "IRAS_REMOTE_ACCESS_ENABLED",
        "IRAS_REMOTE_ACCESS_PERSISTENT", "IRAS_REMOTE_ALLOW_POWER", "IRAS_REMOTE_ALLOW_SHELL",
    ):
        monkeypatch.delenv(name, raising=False)
    policy = RemoteAccessPolicy(tmp_path / "policy.json")
    policy.arm("full", persistent=True, allow_shell=False)
    try:
        policy.authorize("run_command", claimed["arguments"], declared_permission=claimed["permission_level"])
    except PermissionError:
        pass
    else:
        raise AssertionError("full cloud session must not bypass laptop command opt-in")

    policy.arm("full", persistent=True, allow_shell=True)
    assert policy.authorize(
        "run_command", claimed["arguments"], declared_permission=claimed["permission_level"]
    ) == PermissionLevel.CRITICAL
    store.complete(command_id=claimed["command_id"], device_id="windows-e2e-1", ok=True, result={"returncode": 0})
    assert store.get_command(claimed["command_id"])["status"] == "succeeded"
    store.close()
