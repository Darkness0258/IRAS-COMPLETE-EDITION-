from pathlib import Path

from iras.deterministic_orchestration import deterministic_exact_file_direct


OBJECTIVE = (
    'Create D:\\Projects\\IRAS-complete\\multi-agent-test.txt containing exactly '
    '"IRAS v4.2 multi-agent test". Do not modify any other file. Verify the file exists '
    'and contains the exact text, review the operation for safety and correctness, then give me one final report.'
)


def test_direct_exact_file_flow_needs_no_ai_provider():
    calls = []

    def request(action, arguments, timeout):
        calls.append((action, dict(arguments), timeout))
        if action == "write_text":
            return {"bytes": len(arguments["content"].encode())}
        if action == "read_text":
            return {"content": "IRAS v4.2 multi-agent test"}
        if action == "git_status":
            return {"stdout": "## main\n?? multi-agent-test.txt\n"}
        raise AssertionError(action)

    result = deterministic_exact_file_direct(OBJECTIVE, request=request)
    assert result is not None
    assert result["metrics"]["deterministic_direct"] is True
    assert result["metrics"]["model"] == "deterministic-direct-router"
    assert "completed and verified" in result["result"].lower()
    assert [item[0] for item in calls] == ["write_text", "read_text", "git_status"]


def test_cloud_direct_route_checks_deterministic_before_runtime_agent():
    source = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    assert "def _direct_deterministic_response(" in source
    assert "direct_deterministic_candidate = parse_exact_file_objective(body.message) is not None" in source
    assert '"model": "deterministic-direct-router"' in source
    assert "Open Remote, enable a FULL session" in source


def test_direct_exact_file_returns_none_for_general_reasoning():
    called = False

    def request(*_args, **_kwargs):
        nonlocal called
        called = True
        return {}

    assert deterministic_exact_file_direct("Explain dependency graphs", request=request) is None
    assert called is False
