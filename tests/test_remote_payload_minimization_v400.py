from __future__ import annotations

import threading

from iras.device_bridge.store import DeviceBridgeStore


def test_remote_command_payload_is_scrubbed_after_result_delivery(tmp_path):
    store = DeviceBridgeStore(sqlite_path=tmp_path / "bridge.db")
    store.pair_device(
        device_id="windows-scrub-1", display_name="PC", platform="Windows",
        device_token="secret", capabilities=["clipboard_get"], app_version="4.0.0",
    )
    session = store.create_remote_session(device_id="windows-scrub-1", mode="read_only", ttl_seconds=120)
    auth = store.authorize_remote_session(session["session_id"], session["session_token"])

    def device_worker():
        import time
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            cmd = store.claim_next("windows-scrub-1")
            if cmd:
                store.complete(
                    command_id=cmd["command_id"], device_id="windows-scrub-1", ok=True,
                    result={"text": "sensitive clipboard contents"},
                )
                return
            time.sleep(0.01)
        raise AssertionError("command was not queued")

    thread = threading.Thread(target=device_worker)
    thread.start()
    result = store.remote_request_and_wait(
        session=auth, action="clipboard_get", arguments={}, timeout=2,
    )
    thread.join(timeout=2)
    assert result == {"text": "sensitive clipboard contents"}
    row = store.recent_commands("windows-scrub-1", limit=1)[0]
    assert row["arguments"] == {}
    assert row["result"] is None
    store.close()
