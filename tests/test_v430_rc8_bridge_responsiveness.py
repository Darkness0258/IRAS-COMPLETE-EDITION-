from concurrent.futures import ThreadPoolExecutor
import threading
import time

from iras.device_bridge.agent import DeviceBridgeAgent
from iras.device_bridge.store import DeviceBridgeStore


def _paired_store(tmp_path):
    store = DeviceBridgeStore(sqlite_path=tmp_path / "bridge.db")
    store.pair_device(
        device_id="device-rc8-123456",
        display_name="RC8 PC",
        platform="Windows 10",
        device_token="token",
        capabilities=[],
        app_version="4.3.0-rc8",
    )
    return store


def test_claim_next_can_skip_busy_local_llm_lane(tmp_path):
    store = _paired_store(tmp_path)
    store.enqueue(
        action="local_llm_complete",
        arguments={"messages": [{"role": "user", "content": "think"}]},
        device_id="device-rc8-123456",
    )
    store.enqueue(
        action="open_app",
        arguments={"app": "notepad"},
        device_id="device-rc8-123456",
    )

    interactive = store.claim_next(
        "device-rc8-123456",
        exclude_action="local_llm_complete",
    )
    assert interactive is not None
    assert interactive["action"] == "open_app"

    local_ai = store.claim_next("device-rc8-123456")
    assert local_ai is not None
    assert local_ai["action"] == "local_llm_complete"


def test_local_llm_dispatch_does_not_block_bridge_thread():
    agent = DeviceBridgeAgent.__new__(DeviceBridgeAgent)
    agent._local_ai_lock = threading.Lock()
    agent._local_ai_futures = set()
    agent._local_ai_pool = ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="iras-test-local-ai",
    )

    started = threading.Event()
    release = threading.Event()
    calls = []

    def fake_execute(command):
        calls.append(command["action"])
        started.set()
        release.wait(2)

    agent._execute = fake_execute
    try:
        before = time.perf_counter()
        agent._dispatch_local_ai({"action": "local_llm_complete", "command_id": "x"})
        elapsed = time.perf_counter() - before
        assert elapsed < 0.25
        assert started.wait(1)
        assert agent._local_ai_busy() is True
        release.set()
        deadline = time.time() + 2
        while agent._local_ai_busy() and time.time() < deadline:
            time.sleep(0.01)
        assert agent._local_ai_busy() is False
        assert calls == ["local_llm_complete"]
    finally:
        release.set()
        agent._local_ai_pool.shutdown(wait=True, cancel_futures=True)


def test_poll_can_request_local_ai_exclusion():
    class Response:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"command": None}

    class Client:
        def __init__(self):
            self.params = None
        def get(self, url, *, params, headers):
            self.params = params
            return Response()

    agent = DeviceBridgeAgent.__new__(DeviceBridgeAgent)
    agent.server_url = "https://example.invalid"
    agent.client = Client()
    agent.device_id = "device"
    agent.device_token = "token"
    agent._persist = lambda: None

    assert agent._poll(exclude_action="local_llm_complete") is None
    assert agent.client.params["timeout"] == 25
    assert agent.client.params["exclude_action"] == "local_llm_complete"
