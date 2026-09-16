from __future__ import annotations

import pytest

from iras.device_bridge.agent import DeviceBridgeAgent
from iras.device_bridge.store import DeviceBridgeStore


def _store(tmp_path):
    store = DeviceBridgeStore(sqlite_path=tmp_path / "bridge.db")
    store.pair_device(
        device_id="windows-device-12345678",
        display_name="Remote Windows",
        platform="Windows 10",
        device_token="device-secret",
        capabilities=["open_app"],
        app_version="4.0.0-rc2",
    )
    return store


def test_request_timeout_expires_unclaimed_command(tmp_path, monkeypatch):
    store = _store(tmp_path)

    def immediate_timeout(command_id, timeout=30.0):
        return store.get_command(command_id)

    monkeypatch.setattr(store, "wait", immediate_timeout)

    with pytest.raises(RuntimeError, match="did not accept the command"):
        store.request_and_wait(
            action="open_app",
            arguments={"app": "Calculator"},
            timeout=5,
        )

    commands = store.recent_commands("windows-device-12345678")
    assert len(commands) == 1
    assert commands[0]["status"] == "expired"
    assert "Requester timed out" in (commands[0]["error"] or "")
    store.close()


def test_request_ttl_tracks_wait_window(tmp_path, monkeypatch):
    store = _store(tmp_path)

    def immediate_timeout(command_id, timeout=30.0):
        return store.get_command(command_id)

    monkeypatch.setattr(store, "wait", immediate_timeout)

    with pytest.raises(RuntimeError):
        store.request_and_wait(
            action="open_app",
            arguments={"app": "Notepad"},
            timeout=37,
        )

    command = store.recent_commands("windows-device-12345678")[0]
    lifetime = float(command["expires_at"]) - float(command["created_at"])
    assert 36.0 <= lifetime <= 38.5
    store.close()


def test_bridge_still_polls_when_emergency_stop_is_active(tmp_path, monkeypatch):
    # Avoid touching the real user bridge configuration while constructing the
    # agent in this behavior-level regression test.
    monkeypatch.setattr("iras.device_bridge.agent.CONFIG_PATH", tmp_path / "bridge.json")
    agent = DeviceBridgeAgent(
        server_url="https://iras-cloud.example",
        api_token="x" * 40,
    )

    class Stop:
        def tripped(self):
            # End the loop after this first iteration. The body should still
            # poll once so the pending command can be explicitly rejected.
            agent.stop_event.set()
            return True

    class Policy:
        def status(self):
            return {
                "enabled": False,
                "mode": "off",
            }

    seen = []
    agent.emergency_stop = Stop()
    agent.policy = Policy()
    agent.device_token = "paired-token"
    agent._ensure_cloud_compatible = lambda: {}
    agent._poll = lambda: {
        "command_id": "cmd-1",
        "action": "open_app",
        "arguments": {"app": "Calculator"},
    }
    agent._execute = lambda command: seen.append(command)

    agent._run()

    assert seen and seen[0]["command_id"] == "cmd-1"
    agent.client.close()
