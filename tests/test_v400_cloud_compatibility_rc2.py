from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

import iras.device_bridge.agent as bridge_agent
from iras.remote_protocol import (
    IRAS_CLOUD_SERVICE_ID,
    REMOTE_PROTOCOL_VERSION,
    RemoteCompatibilityError,
    validate_cloud_health,
)


def _health(version: str = "4.0.0") -> dict:
    return {
        "ok": True,
        "service": "IRAS Cloud",
        "service_id": IRAS_CLOUD_SERVICE_ID,
        "version": version,
        "remote_protocol": REMOTE_PROTOCOL_VERSION,
    }


def test_current_v4_cloud_health_contract_is_accepted():
    result = validate_cloud_health(_health())
    assert result["compatible"] is True
    assert result["remote_protocol"] == 1
    assert result["version"] == "4.0.0"


def test_old_v3_cloud_is_rejected_before_pairing():
    payload = _health("3.6.0")
    with pytest.raises(RemoteCompatibilityError, match="too old"):
        validate_cloud_health(payload)


def test_missing_remote_protocol_is_rejected():
    payload = _health()
    payload.pop("remote_protocol")
    with pytest.raises(RemoteCompatibilityError, match="protocol"):
        validate_cloud_health(payload)


def test_probe_verifies_health_and_master_token():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health(), request=request)
        if request.url.path == "/v1/devices":
            assert request.headers["Authorization"] == "Bearer correct-token"
            return httpx.Response(200, json={"devices": []}, request=request)
        return httpx.Response(404, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = bridge_agent.probe_remote_cloud(
            "https://iras.example",
            api_token="correct-token",
            client=client,
        )
    finally:
        client.close()

    assert result["compatible"] is True
    assert result["token_verified"] is True


def test_probe_reports_bad_master_token_clearly():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json=_health(), request=request)
        return httpx.Response(401, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RuntimeError, match="rejected IRAS_API_TOKEN"):
            bridge_agent.probe_remote_cloud(
                "https://iras.example",
                api_token="wrong-token",
                client=client,
            )
    finally:
        client.close()


def test_configure_persists_verified_cloud_contract(monkeypatch, tmp_path):
    path = tmp_path / "bridge.json"
    monkeypatch.setattr(bridge_agent, "CONFIG_PATH", path)
    monkeypatch.setattr(
        bridge_agent,
        "probe_remote_cloud",
        lambda server_url, api_token="", client=None: {
            "service_id": "iras-cloud",
            "version": "4.0.0",
            "remote_protocol": 1,
            "compatible": True,
            "token_verified": True,
        },
    )

    result = bridge_agent.configure_remote_bridge(
        server_url="https://iras.example",
        api_token="x" * 32,
    )
    raw = json.loads(path.read_text(encoding="utf-8"))

    assert result["cloud_version"] == "4.0.0"
    assert result["remote_protocol"] == 1
    assert result["token_verified"] is True
    assert raw["cloud_version"] == "4.0.0"
    assert raw["remote_protocol"] == 1
    assert "api_token" not in raw
    assert raw["api_token_protected"]


def test_cloud_health_exposes_v4_remote_contract():
    text = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    health_start = text.index('@app.get("/health")')
    ready_start = text.index('@app.get("/ready")')
    block = text[health_start:ready_start]
    assert '"service_id": IRAS_CLOUD_SERVICE_ID' in block
    assert '"remote_protocol": REMOTE_PROTOCOL_VERSION' in block


def test_pairing_contract_is_bidirectional():
    cloud = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    agent = Path("src/iras/device_bridge/agent.py").read_text(encoding="utf-8")
    assert "body.remote_protocol != REMOTE_PROTOCOL_VERSION" in cloud
    assert '"remote_protocol": REMOTE_PROTOCOL_VERSION' in agent
    assert 'status_code=409' in cloud


def test_direct_bridge_configuration_requires_32_character_token():
    text = Path("src/iras/device_bridge/agent.py").read_text(encoding="utf-8")
    assert "if len(api_token) < 32:" in text
