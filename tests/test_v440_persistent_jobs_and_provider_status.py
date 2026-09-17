from __future__ import annotations

import json
import time

from iras.models import PermissionLevel
from iras.orchestration import OrchestrationManager
from iras.providers.multi_provider import MultiProvider, ProviderSlot
from iras.remote_access import action_permission


class _Provider:
    def __init__(self, model="model"):
        self.model = model
        self.last_request_ms = 0
        self.last_first_token_ms = 0

    def complete(self, messages, tools):
        return {"ok": True}

    def stream_text(self, messages, tools):
        yield "ok"


def test_provider_status_exposes_health_routing_and_timestamps():
    provider = MultiProvider([ProviderSlot("alpha", _Provider("a")), ProviderSlot("beta", _Provider("b"))])
    rows = provider.diagnostics()
    assert rows[0]["state"] == "online"
    assert rows[0]["next"] is True
    assert rows[0]["last_success_at"] is None

    provider.complete([], [])
    rows = provider.diagnostics()
    assert rows[0]["active"] is True
    assert rows[0]["last_success_at"] is not None
    assert rows[0]["latency_ms"] >= 0


def test_provider_status_classifies_rate_limit():
    slot = ProviderSlot("alpha", _Provider())
    provider = MultiProvider([slot], cooldown_seconds=60)
    provider._mark_failed(slot, RuntimeError("LLM HTTP 429: rate limit exceeded"))
    row = provider.diagnostics()[0]
    assert row["state"] == "rate_limited"
    assert row["ready"] is False
    assert row["cooldown_seconds"] > 0


def test_local_llm_status_is_read_only():
    assert action_permission("local_llm_status", {}) == PermissionLevel.READ


def test_restart_checkpoint_preserves_success_and_requires_resume(tmp_path):
    journal = tmp_path / "runs.json"
    journal.write_text(
        json.dumps(
            {
                "version": 2,
                "runs": [
                    {
                        "run_id": "resume123",
                        "objective": "continue safely",
                        "requester_device": "web",
                        "state": "running",
                        "created_at": "2026-09-17T10:00:00+00:00",
                        "started_at": "2026-09-17T10:00:01+00:00",
                        "checkpoint": {
                            "version": 1,
                            "project_root": r"D:\\Projects\\IRAS-complete",
                            "project_device_id": "device",
                            "rollback_checkpoint": {"head": "abc123", "working_tree_clean": True},
                        },
                        "tasks": [
                            {
                                "task_id": "done",
                                "title": "Done",
                                "prompt": "done",
                                "role": "reviewer",
                                "priority": 90,
                                "depends_on": [],
                                "max_retries": 1,
                                "continue_on_failure": False,
                                "state": "succeeded",
                                "attempts": 1,
                                "result": "verified",
                            },
                            {
                                "task_id": "work",
                                "title": "Work",
                                "prompt": "work",
                                "role": "coder",
                                "priority": 80,
                                "depends_on": ["done"],
                                "max_retries": 1,
                                "continue_on_failure": False,
                                "state": "running",
                                "attempts": 1,
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manager = OrchestrationManager(lambda prompt, ctx: {"result": "resumed:" + prompt}, journal_path=journal, max_workers=1)
    try:
        recovered = manager.get("resume123")
        assert recovered["state"] == "interrupted"
        assert recovered["resume_required"] is True
        by_id = {task["task_id"]: task for task in recovered["tasks"]}
        assert by_id["done"]["state"] == "succeeded"
        assert by_id["work"]["state"] == "interrupted"
        assert recovered["checkpoint"]["rollback_checkpoint"]["head"] == "abc123"

        resumed = manager.resume("resume123", context_update={"remote_session": {"session_id": "fresh"}})
        assert resumed["state"] == "running"
        assert resumed["resume_required"] is False
        final = manager.wait("resume123", timeout=3)
        by_id = {task["task_id"]: task for task in final["tasks"]}
        assert by_id["done"]["attempts"] == 1
        assert by_id["work"]["state"] == "succeeded"
        assert any(event["kind"] == "checkpoint_resumed" for event in final["events"])
    finally:
        manager.close()


def test_retry_failed_preserves_successful_checkpoint():
    attempts = {"bad": 0}

    def runner(prompt, context):
        if prompt == "bad":
            attempts["bad"] += 1
            if attempts["bad"] == 1:
                raise RuntimeError("first failure")
        return {"result": "ok:" + prompt}

    manager = OrchestrationManager(runner, max_workers=1, max_tasks_per_run=5)
    try:
        run = manager.submit_graph(
            "retry failed",
            [
                {"id": "good", "prompt": "good", "max_retries": 0},
                {"id": "bad", "prompt": "bad", "depends_on": ["good"], "max_retries": 0},
            ],
            add_coordinator=False,
        )
        first = manager.wait(run["run_id"], timeout=3)
        assert first["state"] == "partial_failure"
        good_attempts = {t["task_id"]: t["attempts"] for t in first["tasks"]}["good"]
        manager.resume(run["run_id"], retry_failed=True)
        second = manager.wait(run["run_id"], timeout=3)
        by_id = {t["task_id"]: t for t in second["tasks"]}
        assert second["state"] == "succeeded"
        assert by_id["good"]["attempts"] == good_attempts
        assert by_id["bad"]["state"] == "succeeded"
    finally:
        manager.close()


def test_web_provider_panel_and_retry_contract():
    text = open("clients/web/index.html", encoding="utf-8").read()
    assert 'id="providers"' in text
    assert 'id="providersDlg"' in text
    assert "/v1/providers/status" in text
    assert 'id="retryGoal"' in text
    assert '"interrupted"' in text
    assert "...remoteHeaders()" in text


def test_provider_panel_deduplicates_concurrent_and_repeated_rows():
    text = open("clients/web/index.html", encoding="utf-8").read()
    assert "providerStatusGeneration" in text
    assert "const providerIndex=new Map()" in text
    assert "providerGrid.replaceChildren(...cards)" in text


def test_provider_status_api_deduplicates_logical_provider_identity():
    text = open("src/iras/cloud_api.py", encoding="utf-8").read()
    assert "def _provider_identity" in text
    assert "def _dedupe_provider_rows" in text
    assert "rows = _dedupe_provider_rows([*cloud, local])" in text


def test_v44_ci_runs_v440_validator():
    text = open(".github/workflows/ci.yml", encoding="utf-8").read()
    assert "IRAS v4.4 RC2 provider status and current release validation" in text
    assert r".\run-v440-validation.ps1" in text
    assert "run-v430-validation.ps1" not in text
