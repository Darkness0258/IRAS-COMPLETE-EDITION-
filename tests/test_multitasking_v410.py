from __future__ import annotations

import time

import pytest

from iras.device_bridge.remote_context import remote_command_context
from iras.device_bridge.tools import make_tools as make_device_tools
from iras.multitasking import (
    MultitaskManager,
    TaskMemoryView,
    parse_parallel_command,
)


class _Memory:
    def __init__(self):
        self.messages = [
            {"role": "user", "content": "baseline"},
            {"role": "assistant", "content": "ready"},
        ]
        self.facts = {"project": "IRAS"}

    def add_message(self, role, content):
        self.messages.append({"role": role, "content": content})

    def recent_messages(self, limit=20):
        return self.messages[-limit:]

    def remember(self, key, value):
        self.facts[key] = value

    def get_fact(self, key, default=None):
        return self.facts.get(key, default)

    def search_facts(self, query, limit=10):
        return [
            {"key": key, "value": value}
            for key, value in self.facts.items()
            if query.lower() in key.lower() or query.lower() in str(value).lower()
        ][:limit]

    def all_facts(self, limit=100):
        return [
            {"key": key, "value": value}
            for key, value in list(self.facts.items())[:limit]
        ]


def test_task_memory_isolates_parallel_conversation_turns():
    base = _Memory()
    seed = base.recent_messages(20)
    left = TaskMemoryView(base, seed_messages=seed)
    right = TaskMemoryView(base, seed_messages=seed)

    left.add_message("user", "left only")
    right.add_message("user", "right only")

    left_text = [item["content"] for item in left.recent_messages(20)]
    right_text = [item["content"] for item in right.recent_messages(20)]

    assert "left only" in left_text
    assert "left only" not in right_text
    assert "right only" in right_text
    assert "right only" not in left_text

    left.remember("shared.fact", "yes")
    assert right.get_fact("shared.fact") == "yes"


def test_multitask_manager_runs_independent_jobs_in_parallel():
    def runner(prompt, _context):
        time.sleep(0.18)
        return {"result": prompt.upper(), "metrics": {"total_ms": 180}}

    manager = MultitaskManager(runner, max_workers=3, max_tasks_per_run=6)
    try:
        started = time.perf_counter()
        run = manager.submit(["one", "two", "three"])
        final = manager.wait(run["run_id"], timeout=3)
        elapsed = time.perf_counter() - started

        assert final["state"] == "succeeded"
        assert [task["result"] for task in final["tasks"]] == ["ONE", "TWO", "THREE"]
        # Sequential execution would be about 0.54s. Leave generous CI headroom.
        assert elapsed < 0.48
    finally:
        manager.close()


def test_multitask_manager_enforces_bounded_batch_size():
    manager = MultitaskManager(
        lambda prompt, context: {"result": prompt},
        max_workers=2,
        max_tasks_per_run=3,
    )
    try:
        with pytest.raises(ValueError, match="at least two"):
            manager.submit(["one"])
        with pytest.raises(ValueError, match="at most 3"):
            manager.submit(["1", "2", "3", "4"])
    finally:
        manager.close()


def test_parallel_chat_syntax_is_explicit_not_heuristic():
    assert parse_parallel_command(
        "/parallel research Python || check my PC || summarize project"
    ) == [
        "research Python",
        "check my PC",
        "summarize project",
    ]
    assert parse_parallel_command(
        "/multitask\nresearch Python\ncheck my PC"
    ) == ["research Python", "check my PC"]
    assert parse_parallel_command(
        "research Python and check my PC at the same time"
    ) == []


class _DeviceStore:
    def __init__(self):
        self.calls = []

    def request_and_wait(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}

    def list_devices(self):
        return []


def test_remote_context_routes_each_parallel_worker_to_its_session_device():
    store = _DeviceStore()
    tools = {tool.name: tool for tool in make_device_tools(store)}

    with remote_command_context(
        {
            "session_id": "session-a",
            "device_id": "device-a",
            "requester_device": "web-a",
        }
    ):
        tools["device_system_info"].handler()

    with remote_command_context(
        {
            "session_id": "session-b",
            "device_id": "device-b",
            "requester_device": "web-b",
        }
    ):
        tools["device_system_info"].handler()

    assert store.calls[0]["device_id"] == "device-a"
    assert store.calls[0]["remote_session_id"] == "session-a"
    assert store.calls[1]["device_id"] == "device-b"
    assert store.calls[1]["remote_session_id"] == "session-b"


def test_web_and_cloud_expose_multitask_controls():
    from pathlib import Path

    api = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    web = Path("clients/web/index.html").read_text(encoding="utf-8")

    assert '"/v1/multitask/runs"' in api
    assert '"/v1/multitask/runs/{run_id}"' in api
    assert 'id="tasks"' in web
    assert "runParallelTasks" in web
