from iras.device_bridge.store import DeviceBridgeStore


def test_pair_authorize_queue_claim_complete(tmp_path):
    store = DeviceBridgeStore(sqlite_path=tmp_path / "bridge.db")

    secret = "device-secret-test"

    store.pair_device(
        device_id="device-12345678",
        display_name="My PC",
        platform="Windows 10",
        device_token=secret,
        capabilities=["system_info", "open_app"],
        app_version="2.6.0",
    )

    assert store.authorize_device("device-12345678", secret)
    assert not store.authorize_device("device-12345678", "wrong-secret")

    devices = store.list_devices()
    assert len(devices) == 1
    assert devices[0]["online"]
    assert "token_hash" not in devices[0]

    queued = store.enqueue(
        action="system_info",
        arguments={},
        device_id="device-12345678",
    )

    claimed = store.claim_next("device-12345678")
    assert claimed["command_id"] == queued["command_id"]
    assert claimed["action"] == "system_info"

    completed = store.complete(
        command_id=queued["command_id"],
        device_id="device-12345678",
        ok=True,
        result={"os": "Windows"},
    )

    assert completed["status"] == "succeeded"
    assert completed["result"]["os"] == "Windows"

    store.close()
