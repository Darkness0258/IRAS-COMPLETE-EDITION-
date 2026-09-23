from __future__ import annotations

from pathlib import Path

from iras.cloud_state import CloudStateStore
from iras.v5.common import SQLiteDB
from iras.v5.runtime import FEATURES


def store(tmp_path):
    return CloudStateStore(SQLiteDB(tmp_path / "cloud.db"))


def test_cloud_workspace_is_feature_family():
    assert "unified_cloud_workspace" in FEATURES
    assert len(FEATURES) == 36


def test_cloud_clients_share_one_active_thread_and_history(tmp_path):
    state = store(tmp_path)
    web = state.register_client(
        client_id="web_test",
        name="IRAS Web",
        platform="web",
        app_version="5.0.0-rc11",
        capabilities=["chat", "cloud-sync"],
    )
    android = state.register_client(
        client_id="android_test",
        name="IRAS Android",
        platform="android",
        app_version="5.0.0-rc11",
        capabilities=["chat", "approvals"],
    )
    assert web["active_thread_id"] == android["active_thread_id"]
    thread_id = web["active_thread_id"]
    state.add_message(thread_id, "user", "hello from web", client_id="web_test", request_id="turn_1")
    state.add_message(thread_id, "assistant", "hello from IRAS", client_id="web_test", request_id="req_1")
    snapshot = state.snapshot(thread_id=thread_id)
    assert [row["content"] for row in snapshot["messages"]] == ["hello from web", "hello from IRAS"]
    assert {row["platform"] for row in snapshot["clients"]} >= {"web", "android"}


def test_cloud_turn_id_deduplicates_client_retry(tmp_path):
    state = store(tmp_path)
    thread = state.ensure_thread()
    first = state.add_message(thread["thread_id"], "user", "do this", client_id="web_x", request_id="turn_same")
    second = state.add_message(thread["thread_id"], "user", "do this", client_id="web_x", request_id="turn_same")
    assert first["message_id"] == second["message_id"]
    assert len(state.messages(thread["thread_id"])) == 1


def test_cloud_workspace_survives_restart(tmp_path):
    db_path = tmp_path / "cloud.db"
    first = CloudStateStore(SQLiteDB(db_path))
    thread = first.create_thread("Persistent cloud")
    first.activate_thread(thread["thread_id"])
    first.set_preference("voice_enabled", True)
    first.add_message(thread["thread_id"], "user", "persist me", request_id="turn_persist")

    second = CloudStateStore(SQLiteDB(db_path))
    assert second.active_thread_id() == thread["thread_id"]
    assert second.get_preference("voice_enabled") is True
    assert second.messages(thread["thread_id"])[0]["content"] == "persist me"


def test_cloud_source_exposes_cross_client_contract():
    root = Path(__file__).resolve().parents[1]
    cloud = (root / "src" / "iras" / "cloud_api.py").read_text(encoding="utf-8")
    for route in (
        "/v1/cloud/clients/register",
        "/v1/cloud/clients/{client_id}/heartbeat",
        "/v1/cloud/session",
        "/v1/cloud/threads",
        "/v1/cloud/threads/{thread_id}/messages",
        "/v1/cloud/preferences",
    ):
        assert route in cloud
    assert "client_id: str = Field" in cloud
    assert "thread_id: str = Field" in cloud
    assert "turn_id: str = Field" in cloud
    assert "persisted_events" in cloud


def test_windows_web_android_all_join_cloud_workspace():
    root = Path(__file__).resolve().parents[1]
    web = (root / "clients" / "web" / "index.html").read_text(encoding="utf-8")
    android = (root / "clients" / "android" / "app" / "src" / "main" / "java" / "com" / "darkness" / "iras" / "MainActivity.java").read_text(encoding="utf-8")
    pc = (root / "src" / "iras" / "cloud_client.py").read_text(encoding="utf-8")
    project = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert "/v1/cloud/clients/register" in web
    assert "iras-cloud-thread-id" in web
    assert 'thread_id:cloudThreadId()' in web
    assert 'turn_id:turnId' in web

    assert "/v1/cloud/clients/register" in android
    assert '"cloud_thread_id"' in android
    assert '"thread_id"' in android
    assert '"turn_id"' in android

    assert "/v1/cloud/clients/register" in pc
    assert "/v1/cloud/threads" in pc
    assert '"thread_id": thread_id' in pc
    assert 'iras-cloud-client = "iras.cloud_client:main"' in project
    assert (root / "run-iras-cloud-client.ps1").exists()


def test_cloud_state_does_not_store_authentication_secrets():
    source = Path("src/iras/cloud_state.py").read_text(encoding="utf-8").lower()
    assert "api_token" not in source
    assert "device_token" not in source
    assert "authorization" not in source


def test_agent_accepts_request_scoped_cloud_history_override():
    from iras.core.agent import IRASAgent

    class Memory:
        def all_facts(self, limit):
            return []
        def recent_messages(self, limit):
            return [{"role": "user", "content": "global history must not leak"}]

    agent = IRASAgent(None, None, Memory(), None, context_message_limit=8)
    agent.context_messages_override = [
        {"role": "user", "content": "cloud thread question"},
        {"role": "assistant", "content": "cloud thread answer"},
    ]
    messages = agent._base_messages("next")
    contents = [str(item.get("content") or "") for item in messages]
    assert "cloud thread question" in contents
    assert "cloud thread answer" in contents
    assert "global history must not leak" not in contents


def test_web_and_android_poll_cloud_for_cross_device_updates():
    root = Path(__file__).resolve().parents[1]
    web = (root / "clients" / "web" / "index.html").read_text(encoding="utf-8")
    android = (root / "clients" / "android" / "app" / "src" / "main" / "java" / "com" / "darkness" / "iras" / "MainActivity.java").read_text(encoding="utf-8")
    assert "syncCloudMessages" in web
    assert "setInterval(()=>syncCloudMessages" in web
    assert "assistant_message_id" in web
    assert "user_message_id" in web
    assert "syncCloudMessagesOnce" in android
    assert "cloudRenderedMessageIds" in android
    assert "assistant_message_id" in android
    assert "user_message_id" in android


def test_windows_cloud_client_does_not_inherit_public_base_url(monkeypatch):
    from iras.cloud_client import _server

    class DummySettings:
        public_base_url = "http://127.0.0.1:8765"

    monkeypatch.delenv("IRAS_CLOUD_URL", raising=False)
    assert _server(DummySettings()) == "https://iras-cloud.onrender.com"

    monkeypatch.setenv("IRAS_CLOUD_URL", "https://cloud.example.test/")
    assert _server(DummySettings()) == "https://cloud.example.test"
    assert _server(DummySettings(), "https://override.example.test/") == "https://override.example.test"
