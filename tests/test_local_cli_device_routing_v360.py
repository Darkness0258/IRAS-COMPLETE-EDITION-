from __future__ import annotations

from pathlib import Path

from iras.config import Settings
from iras.bootstrap import build_runtime
from iras.core.agent import IRASAgent
from iras.device_bridge.intent import direct_device_intent
from iras.device_bridge.local_store import LocalDeviceBridgeStore
from iras.device_bridge.tools import make_tools


class _FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, action, arguments):
        self.calls.append((action, dict(arguments)))
        return {"ok": True, "action": action, "arguments": dict(arguments)}


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        provider="demo",
        model="demo",
        api_key="",
        base_url="http://127.0.0.1:1/v1",
        request_timeout=5.0,
        auto_permission_level=1,
        always_confirm_critical=True,
        api_token="test",
        node_token="test",
        node_max_permission_level=1,
        tts_provider="windows",
        voice="en-US-JennyNeural",
        stt_provider="whisper_local",
        whisper_model="base.en",
        listen_seconds=1,
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        max_agent_steps=8,
        system_name="IRAS",
        voice_replies=False,
        voice_profile="anime_soft",
        adaptive_personality=False,
        database_url="",
        public_base_url="",
        cors_origins="*",
    )


def test_local_device_store_uses_bounded_executor_contract():
    fake = _FakeExecutor()
    store = LocalDeviceBridgeStore(fake)

    result = store.request_and_wait(
        action="computer_observe",
        arguments={"vision": "off", "scope": "foreground"},
    )

    assert result["ok"] is True
    assert fake.calls == [
        ("computer_observe", {"vision": "off", "scope": "foreground"})
    ]
    assert store.list_devices()[0]["local"] is True


def test_local_runtime_registers_computer_use_tools(tmp_path):
    runtime = build_runtime(_settings(tmp_path))
    names = set(runtime.registry.names())

    assert "device_open_app" in names
    assert "device_computer_observe" in names
    assert "device_computer_action" in names
    assert "device_computer_verify" in names
    assert "device_whatsapp_open_chat" in names


def test_local_device_turn_does_not_expose_run_shell():
    agent = IRASAgent(None, None, None, None, smart_tools=False)

    names = agent._smart_tool_names(
        "Open Notepad and bring it to the foreground. Do not type anything."
    )

    assert names is not None
    assert "device_open_app" in names
    assert "run_shell" not in names
    assert "device_computer_action" not in names


def test_foreground_observation_is_read_only_at_schema_layer():
    agent = IRASAgent(None, None, None, None, smart_tools=False)

    names = set(
        agent._smart_tool_names(
            "Observe the current foreground window and tell me its title and "
            "whether UI Automation is actionable. Do not click or type."
        )
    )

    assert names == {"device_computer_observe", "device_computer_status"}


def test_negated_spotify_play_does_not_route_to_playback():
    agent = IRASAgent(None, None, None, None, smart_tools=False)

    names = set(
        agent._smart_tool_names(
            "Open Spotify and bring it to the foreground. Do not play anything yet."
        )
    )

    assert "device_spotify_play" not in names
    assert "device_open_app" in names
    assert "device_computer_action" not in names


def test_spotify_play_verification_clause_is_not_part_of_query():
    action = direct_device_intent(
        "Play Blinding Lights by The Weeknd in Spotify, then verify from the "
        "current UI state that playback actually started."
    )

    assert action == {
        "tool": "device_spotify_play",
        "arguments": {"query": "Blinding Lights by The Weeknd"},
        "kind": "spotify_play",
    }


def test_spotify_pause_with_verification_routes_to_media_control():
    action = direct_device_intent(
        "Pause Spotify and verify from the current UI state that playback is paused."
    )

    assert action == {
        "tool": "device_media_control",
        "arguments": {"command": "pause", "app": "spotify"},
        "kind": "media_control",
    }


def test_local_spotify_fastpath_accepts_shared_device_store_metadata():
    fake = _FakeExecutor()
    store = LocalDeviceBridgeStore(fake)
    tools = make_tools(store)
    spotify = next(item for item in tools if item.name == "device_spotify_play")

    result = spotify.handler(query="naat")

    assert result["ok"] is True
    assert fake.calls[-1] == ("spotify_play", {"query": "naat"})


def test_local_store_rejects_remote_session_provenance():
    store = LocalDeviceBridgeStore(_FakeExecutor())
    import pytest

    with pytest.raises(PermissionError):
        store.request_and_wait(
            action="system_info",
            arguments={},
            remote_session_id="remote-session",
            permission_level=2,
        )
