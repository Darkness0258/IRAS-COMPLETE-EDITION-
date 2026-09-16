from iras.security.secret_store import protect_secret, unprotect_secret, protection_backend


def test_secret_store_roundtrip_and_nonplaintext():
    value = "super-secret-validation-token"
    protected = protect_secret(value)
    assert protected != value
    assert unprotect_secret(protected) == value
    assert protection_backend() in {"windows-dpapi", "plain-test-fallback"}


def test_secret_store_accepts_legacy_plaintext_for_migration():
    assert unprotect_secret("legacy-token") == "legacy-token"


def test_remote_bridge_config_migrates_legacy_plaintext_secrets(monkeypatch, tmp_path):
    import json
    import iras.device_bridge.agent as bridge_agent

    config_path = tmp_path / "bridge.json"
    config_path.write_text(
        json.dumps(
            {
                "device_id": "legacy-device-id",
                "device_token": "legacy-device-token",
                "api_token": "legacy-api-token",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bridge_agent, "CONFIG_PATH", config_path)

    bridge_agent.configure_remote_bridge(
        server_url="https://iras-cloud.test",
        api_token="new-master-token-abcdefghijklmnopqrstuvwxyz123456",
    )

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert "device_token" not in raw
    assert "api_token" not in raw
    assert raw["device_token_protected"]
    assert raw["api_token_protected"]
    assert unprotect_secret(raw["device_token_protected"]) == "legacy-device-token"
    assert unprotect_secret(raw["api_token_protected"]) == "new-master-token-abcdefghijklmnopqrstuvwxyz123456"
