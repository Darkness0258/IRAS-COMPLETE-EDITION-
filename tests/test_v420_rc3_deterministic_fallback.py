from iras.deterministic_orchestration import (
    deterministic_exact_file_task,
    exact_file_plan,
    parse_exact_file_objective,
)
from iras.orchestration import OrchestrationManager


OBJECTIVE = (
    'Create D:\\Projects\\IRAS-complete\\multi-agent-test.txt containing exactly '
    '"IRAS v4.2 multi-agent test". Do not modify any other file. Verify the file exists '
    'and contains the exact text, review the operation for safety and correctness, then give me one final report.'
)


def test_exact_file_objective_has_deterministic_plan():
    parsed = parse_exact_file_objective(OBJECTIVE)
    assert parsed is not None
    assert parsed.path == r"D:\Projects\IRAS-complete\multi-agent-test.txt"
    assert parsed.content == "IRAS v4.2 multi-agent test"
    plan = exact_file_plan(OBJECTIVE)
    assert [task["role"] for task in plan] == ["coder", "tester", "reviewer"]
    assert plan[1]["depends_on"] == ["create-file"]
    assert plan[2]["depends_on"] == ["verify-file"]


def test_deterministic_exact_file_roles_need_no_model():
    calls = []

    def request(action, arguments, timeout):
        calls.append((action, arguments, timeout))
        if action == "write_text":
            return {"path": arguments["path"], "bytes": len(arguments["content"].encode())}
        if action == "read_text":
            return {"path": arguments["path"], "content": "IRAS v4.2 multi-agent test"}
        if action == "git_status":
            return {"returncode": 0, "stdout": "## main\n?? multi-agent-test.txt\n", "stderr": ""}
        raise AssertionError(action)

    coder = deterministic_exact_file_task(
        role="coder", objective=OBJECTIVE, dependency_results=[], request=request
    )
    tester = deterministic_exact_file_task(
        role="tester", objective=OBJECTIVE, dependency_results=[], request=request
    )
    reviewer = deterministic_exact_file_task(
        role="reviewer", objective=OBJECTIVE, dependency_results=[], request=request
    )
    coordinator = deterministic_exact_file_task(
        role="coordinator",
        objective=OBJECTIVE,
        dependency_results=[
            {"task_id": "create-file", "title": "Create", "state": "succeeded", "result": coder["result"], "error": ""},
            {"task_id": "verify-file", "title": "Verify", "state": "succeeded", "result": tester["result"], "error": ""},
            {"task_id": "review-operation", "title": "Review", "state": "succeeded", "result": reviewer["result"], "error": ""},
        ],
        request=request,
    )
    assert coder["metrics"]["deterministic_fallback"] is True
    assert tester["metrics"]["exact_match"] is True
    assert reviewer["metrics"]["unrelated_change_count"] == 0
    assert "completed and verified" in coordinator["result"].lower()
    assert [call[0] for call in calls] == ["write_text", "read_text", "git_status"]


def test_exact_file_plan_runs_through_dag_without_provider_calls():
    calls = []

    def request(action, arguments, timeout):
        calls.append(action)
        if action == "write_text":
            return {"bytes": len(arguments["content"].encode())}
        if action == "read_text":
            return {"content": "IRAS v4.2 multi-agent test"}
        if action == "git_status":
            return {"stdout": "## main\n?? multi-agent-test.txt\n"}
        raise AssertionError(action)

    def runner(_prompt, context):
        result = deterministic_exact_file_task(
            role=context["agent_role"],
            objective=context["objective"],
            dependency_results=context["dependency_results"],
            request=request,
        )
        assert result is not None
        return result

    manager = OrchestrationManager(runner, max_workers=2, max_tasks_per_run=8)
    try:
        run = manager.submit_graph(OBJECTIVE, exact_file_plan(OBJECTIVE), add_coordinator=True)
        final = manager.wait(run["run_id"], timeout=3)
        assert final["state"] == "succeeded"
        assert all(task["state"] == "succeeded" for task in final["tasks"])
        assert "completed and verified" in final["final_result"].lower()
        assert calls == ["write_text", "read_text", "git_status"]
    finally:
        manager.close()
