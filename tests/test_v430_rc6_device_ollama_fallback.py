from __future__ import annotations

import json

import pytest

from iras.device_bridge.executor import DeviceExecutor
from iras.models import PermissionLevel, ProviderReply
from iras.providers.device_ollama import DeviceOllamaProvider
from iras.providers.multi_provider import MultiProvider, ProviderSlot
from iras.remote_access import action_permission


def test_local_llm_remote_action_is_read_only():
    assert action_permission("local_llm_complete", {}) == PermissionLevel.READ


def test_device_ollama_provider_normalizes_tool_calls():
    calls = []

    def request(action, arguments, timeout):
        calls.append((action, arguments, timeout))
        return {
            "model": "qwen2.5-coder:7b",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "device_git_status",
                    "arguments": json.dumps({"repo": "."}),
                }
            ],
        }

    provider = DeviceOllamaProvider(request, timeout=80)
    reply = provider.complete(
        [{"role": "user", "content": "inspect"}],
        [{"type": "function", "function": {"name": "device_git_status", "parameters": {"type": "object"}}}],
    )
    assert reply.tool_calls[0].name == "device_git_status"
    assert reply.tool_calls[0].arguments == {"repo": "."}
    assert calls[0][0] == "local_llm_complete"
    assert calls[0][2] == 80
    assert provider.last_response_model == "qwen2.5-coder:7b"


def test_hybrid_provider_falls_back_from_cloud_pool_to_device_ollama():
    class DownCloud:
        model = "cloud"

        def complete(self, messages, tools):
            raise RuntimeError(
                "ALL_PROVIDERS_UNAVAILABLE: all configured AI providers are temporarily unavailable. Retry in about 55s."
            )

        def close(self):
            return None

    local = DeviceOllamaProvider(
        lambda action, arguments, timeout: {
            "model": "qwen2.5-coder:7b",
            "content": "Local fallback recovered.",
            "tool_calls": [],
        }
    )
    provider = MultiProvider(
        [
            ProviderSlot("cloud-pool", DownCloud()),
            ProviderSlot("device-ollama", local),
        ],
        cooldown_seconds=5,
    )
    reply = provider.complete([{"role": "user", "content": "hello"}], [])
    assert isinstance(reply, ProviderReply)
    assert reply.text == "Local fallback recovered."
    assert provider.last_provider == "device-ollama"


def test_executor_local_llm_is_loopback_only(monkeypatch):
    executor = DeviceExecutor.__new__(DeviceExecutor)
    monkeypatch.setenv("IRAS_DEVICE_OLLAMA_BASE_URL", "https://example.com/v1")
    with pytest.raises(PermissionError, match="loopback"):
        DeviceExecutor.local_llm_complete(
            executor,
            [{"role": "user", "content": "hello"}],
            [],
        )


def test_executor_local_llm_discovers_model_and_returns_tools(monkeypatch):
    executor = DeviceExecutor.__new__(DeviceExecutor)
    monkeypatch.setenv("IRAS_DEVICE_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")

    class Response:
        def __init__(self, status_code, data):
            self.status_code = status_code
            self._data = data
            self.text = json.dumps(data)

        def json(self):
            return self._data

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.post_payload = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            assert url.endswith("/api/tags")
            return Response(200, {"models": [{"name": "qwen2.5-coder:7b"}]})

        def post(self, url, json=None):
            assert url.endswith("/v1/chat/completions")
            assert json["model"] == "qwen2.5-coder:7b"
            return Response(
                200,
                {
                    "model": "qwen2.5-coder:7b",
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "x",
                                        "function": {
                                            "name": "device_git_status",
                                            "arguments": '{"repo":"."}',
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                },
            )

    import iras.device_bridge.executor as executor_module

    monkeypatch.setattr(executor_module.httpx, "Client", FakeClient)
    result = DeviceExecutor.local_llm_complete(
        executor,
        [{"role": "user", "content": "inspect"}],
        [{"type": "function", "function": {"name": "device_git_status", "parameters": {"type": "object"}}}],
    )
    assert result["model"] == "qwen2.5-coder:7b"
    assert result["local"] is True
    assert result["tool_calls"][0]["name"] == "device_git_status"
