from __future__ import annotations

from pathlib import Path

from iras.device_bridge.tools import make_tools, _spotify_cloud_visual_verification
from iras.providers.device_ollama import DeviceOllamaProvider


class _SpotifyStore:
    def __init__(self):
        self.calls = []

    def list_devices(self):
        return []

    def request_and_wait(self, **kwargs):
        action = kwargs["action"]
        args = dict(kwargs.get("arguments") or {})
        self.calls.append((action, args))
        if action == "spotify_play":
            # Simulate an older bridge that performed the action but did not
            # return the RC3 verified_playback contract.
            return {"app": "spotify", "query": args["query"], "command_sent": True}
        if action == "computer_observe":
            return {
                "foreground": {
                    "title": "Spotify Premium",
                    "rect": {"left": 0, "top": 0, "width": 1600, "height": 900},
                },
                "vision_status": "ready",
                "vision_available": True,
                "vision_element_count": 3,
                "elements": [
                    {"label": "Pause", "role": "button", "rect": {"left": 760, "top": 820, "width": 40, "height": 40}},
                    {"label": "Maa - Naat", "role": "text", "rect": {"left": 1310, "top": 420, "width": 180, "height": 35}},
                    {"label": "Library", "role": "text", "rect": {"left": 40, "top": 100, "width": 90, "height": 30}},
                ],
            }
        raise AssertionError(action)


def test_spotify_cloud_visual_fallback_upgrades_legacy_result_to_verified():
    store = _SpotifyStore()
    tool = {item.name: item for item in make_tools(store)}["device_spotify_play"]
    out = tool.handler(query="maa")
    assert out["verified_playback"] is True
    assert out["verification_source"] == "cloud_agent_computer_observe"
    assert out["playback_verification"]["playing"] is True
    assert out["playback_verification"]["query_match"] is True
    assert [name for name, _ in store.calls] == ["spotify_play", "computer_observe"]


def test_spotify_cloud_visual_fallback_rejects_unrelated_playback():
    obs = {
        "foreground": {
            "title": "Spotify",
            "rect": {"left": 0, "top": 0, "width": 1600, "height": 900},
        },
        "elements": [
            {"label": "Pause", "rect": {"left": 760, "top": 820, "width": 40, "height": 40}},
            {"label": "Through The Skies", "rect": {"left": 1310, "top": 420, "width": 220, "height": 35}},
            # Query text is only in the library, not the now-playing region.
            {"label": "Heart touching naat sharif", "rect": {"left": 30, "top": 250, "width": 220, "height": 35}},
        ],
    }
    result = _spotify_cloud_visual_verification("naat", obs)
    assert result["playing"] is True
    assert result["query_match"] is False
    assert result["verified"] is False


def test_device_ollama_supports_one_chunk_streaming_fallback():
    calls = []

    def request(action, arguments, timeout):
        calls.append((action, arguments, timeout))
        assert action == "local_llm_complete"
        return {"model": "qwen2.5-coder:7b", "content": "local fallback reply", "tool_calls": []}

    provider = DeviceOllamaProvider(request, model="qwen2.5-coder:7b", timeout=20)
    chunks = list(provider.stream_text([{"role": "user", "content": "hello"}], []))
    assert chunks == ["local fallback reply"]
    assert calls


def test_cloud_agent_contract_exposes_device_ollama_and_status_command():
    root = Path(__file__).resolve().parents[1]
    cloud = (root / "src" / "iras" / "cloud_api.py").read_text(encoding="utf-8")
    client = (root / "src" / "iras" / "cloud_client.py").read_text(encoding="utf-8")
    assert "def _cloud_agent_provider_scope(" in cloud
    assert 'ProviderSlot("device-ollama", local_provider)' in cloud
    assert '"/v1/agent/status"' in cloud
    assert '"spotify_semantic_verify"' in cloud
    assert '/agent' in client


def test_spotify_cloud_visual_rejects_query_as_artist_substring():
    obs = {
        "foreground": {
            "title": "Spotify",
            "rect": {"left": 0, "top": 0, "width": 1600, "height": 900},
        },
        "elements": [
            {"label": "Pause", "rect": {"left": 760, "top": 820, "width": 40, "height": 40}},
            {"label": "savera", "rect": {"left": 1310, "top": 420, "width": 180, "height": 35}},
            {"label": "Maanu", "rect": {"left": 1310, "top": 470, "width": 180, "height": 35}},
        ],
    }
    result = _spotify_cloud_visual_verification("maa", obs)
    assert result["playing"] is True
    assert result["query_match"] is False
    assert result["verified"] is False


def test_spotify_cloud_visual_accepts_exact_query_token():
    obs = {
        "foreground": {
            "title": "Spotify",
            "rect": {"left": 0, "top": 0, "width": 1600, "height": 900},
        },
        "elements": [
            {"label": "Pause", "rect": {"left": 760, "top": 820, "width": 40, "height": 40}},
            {"label": "Maa", "rect": {"left": 1310, "top": 420, "width": 180, "height": 35}},
            {"label": "Shankar Mahadevan", "rect": {"left": 1310, "top": 470, "width": 220, "height": 35}},
        ],
    }
    result = _spotify_cloud_visual_verification("maa", obs)
    assert result["playing"] is True
    assert result["query_match"] is True
    assert result["verified"] is True
