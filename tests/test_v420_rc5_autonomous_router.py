from pathlib import Path

from iras.execution_router import decide_execution, parallel_graph


def test_router_keeps_simple_commands_direct():
    assert decide_execution("hello").mode == "direct"
    assert decide_execution("Open Spotify and play naat").mode == "direct"
    assert decide_execution("Research X and summarize it").mode == "direct"


def test_router_chooses_deterministic_exact_file_without_provider():
    decision = decide_execution(
        'Create D:\\Projects\\IRAS-complete\\direct-test.txt containing exactly "IRAS direct mode works"'
    )
    assert decision.mode == "deterministic"
    assert "provider-independent" in decision.reason


def test_router_chooses_parallel_for_independent_jobs_without_slash_command():
    decision = decide_execution(
        "Research the latest framework changes, check the status of my Windows PC, "
        "and summarize the current project state"
    )
    assert decision.mode == "parallel"
    assert len(decision.tasks) == 3
    graph = parallel_graph(decision.tasks)
    assert len(graph) == 3
    assert {item["role"] for item in graph} >= {"researcher", "tester"}
    assert all(item["depends_on"] == [] for item in graph)


def test_router_can_parallelize_two_clearly_independent_jobs():
    decision = decide_execution("Check my Windows PC status and research Python changes")
    assert decision.mode == "parallel"
    assert len(decision.tasks) == 2


def test_router_chooses_orchestration_for_dependency_heavy_workflow():
    decision = decide_execution(
        "Improve IRAS voice latency, inspect the current implementation, make the safest useful changes, "
        "run tests, review regressions, and report the final result."
    )
    assert decision.mode == "orchestrate"


def test_explicit_commands_remain_api_overrides():
    assert decide_execution("/goal Build and test IRAS").mode == "direct"
    assert decide_execution("/parallel research X || check Y").mode == "direct"


def test_cloud_chat_has_autonomous_parallel_and_orchestration_branches():
    source = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    assert "def _auto_decision(" in source
    assert 'decision.mode == "orchestrate"' in source
    assert 'decision.mode == "parallel"' in source
    assert "_start_auto_parallel_graph(" in source
    assert '"autonomous_execution_decision"' in source
    assert '"autonomous-parallel-router"' in source
    assert '"autonomous-execution-router"' in source


def test_tasks_and_chat_prompt_for_remote_before_exact_file_write():
    web = Path("clients/web/index.html").read_text(encoding="utf-8")
    cloud = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    assert "ensureRemoteForDeterministicWrite" in web
    assert "await ensureRemoteForDeterministicWrite(objective)" in web
    assert "await ensureRemoteForDeterministicWrite(text)" in web
    assert '...remoteHeaders()' in web
    assert "if(data.orchestration_run_id)activeGoalRunId=data.orchestration_run_id" in web
    assert "This goal changes Windows state and requires a live IRAS Remote session" in cloud


def test_doctor_reports_autonomous_execution_routing():
    source = Path("src/iras/doctor.py").read_text(encoding="utf-8")
    assert '"Autonomous execution routing"' in source
    assert "IRAS_AUTONOMOUS_EXECUTION" in source
