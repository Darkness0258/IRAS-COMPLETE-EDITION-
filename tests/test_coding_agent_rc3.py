from pathlib import Path

from iras.coding_agent import (
    CODING_AGENT_TOOL_ALLOWLIST,
    build_coding_agent_graph,
    coding_agent_status,
    is_coding_agent_objective,
)
from iras.models import PermissionLevel
from iras.remote_access import action_permission


def test_coding_agent_detects_real_engineering_objectives_without_hijacking_general_requests():
    assert is_coding_agent_objective("fix the login bug in my IRAS project and run tests") is True
    assert is_coding_agent_objective("refactor the Python backend module") is True
    assert is_coding_agent_objective("/code add a health endpoint to D:\\Projects\\IRAS-complete") is True
    assert is_coding_agent_objective("open spotify and play maa") is False
    assert is_coding_agent_objective("tell me how Python decorators work") is False


def test_coding_agent_graph_has_inspect_implement_test_repair_verify_review_sequence():
    graph = build_coding_agent_graph("fix the parser bug in my project")
    ids = [item["id"] for item in graph]
    assert ids == [
        "code-inspect",
        "code-implement",
        "code-test",
        "code-repair",
        "code-final-test",
        "code-review",
    ]
    assert graph[1]["role"] == "coder"
    assert graph[2]["role"] == "tester"
    assert graph[3]["continue_on_failure"] is True
    assert graph[4]["continue_on_failure"] is True
    assert graph[5]["role"] == "reviewer"


def test_coding_agent_windows_tool_surface_is_powerful_but_excludes_default_power_destructive_controls():
    required = {
        "device_open_project",
        "device_open_app",
        "device_observe_ui",
        "device_computer_observe",
        "device_computer_action",
        "device_computer_verify",
        "device_semantic_action",
        "device_interact_app",
        "device_run_command",
        "device_clipboard_get",
        "device_clipboard_set",
        "device_list_processes",
    }
    assert required.issubset(CODING_AGENT_TOOL_ALLOWLIST)
    assert "device_power_action" not in CODING_AGENT_TOOL_ALLOWLIST
    assert "device_kill_process" not in CODING_AGENT_TOOL_ALLOWLIST
    assert "device_delete_path" not in CODING_AGENT_TOOL_ALLOWLIST


def test_windows_coding_controls_keep_existing_permission_levels():
    assert action_permission("computer_observe", {}) == PermissionLevel.READ
    assert action_permission("computer_action", {"action": "click"}) == PermissionLevel.SYSTEM_ACTION
    assert action_permission("run_command", {"executable": "python"}) == PermissionLevel.CRITICAL


def test_coding_agent_status_declares_permissioned_windows_control():
    status = coding_agent_status()
    assert status["enabled"] is True
    assert status["mode"] == "dedicated_engineering_agent"
    assert status["windows_control"]["enabled"] is True
    assert status["windows_control"]["permissioned"] is True
    assert "device_run_command" in status["windows_control"]["tools"]


def test_cloud_exposes_first_class_coding_agent_endpoints_and_chat_routing():
    cloud = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    assert '@app.get("/v1/coding-agent/status")' in cloud
    assert '@app.post("/v1/coding-agent/runs")' in cloud
    assert '@app.get("/v1/coding-agent/runs/{run_id}")' in cloud
    assert "build_coding_agent_graph" in cloud
    assert "is_coding_agent_objective" in cloud
    assert '"coding_agent_router"' not in cloud  # spelling remains hyphenated in metrics
    assert '"coding-agent-router"' in cloud


def test_windows_cloud_client_has_code_start_and_status_commands():
    client = Path("src/iras/cloud_client.py").read_text(encoding="utf-8")
    assert "/code <goal>" in client
    assert '"/v1/coding-agent/runs"' in client
    assert '"/v1/coding-agent/status"' in client
    assert "last_code_run_id" in client


def test_coder_directive_prefers_bounded_tools_and_respects_permission_failures():
    orchestration = Path("src/iras/orchestration.py").read_text(encoding="utf-8")
    assert "permissioned Windows controls" in orchestration
    assert "device_run_command is CRITICAL" in orchestration
    assert "never " in orchestration and "attempt to bypass permission failures" in orchestration


def test_local_runtime_routes_coding_agent_through_master_permissioned_workers():
    bootstrap = Path("src/iras/bootstrap.py").read_text(encoding="utf-8")
    assert 'if context.get("coding_agent")' in bootstrap
    assert "build_coding_agent_graph(objective)" in bootstrap
    assert "coding_agent_role_allowlist" in bootstrap
    assert "master_autonomy" in bootstrap


def test_local_cli_and_desktop_expose_code_command_without_bypassing_master_control():
    cli = Path("src/iras/cli.py").read_text(encoding="utf-8")
    desktop = Path("src/iras/desktop.py").read_text(encoding="utf-8")
    assert "/code <goal>" in cli
    assert "Local Coding Agent execution requires Master Control" in cli
    assert 'lower.startswith("/code ")' in desktop
    assert "Local Coding Agent execution requires Master Control" in desktop


def test_coding_agent_project_name_parser_handles_name_before_project_and_explicit_paths():
    from iras.coding_agent import extract_windows_project_path, project_query_from_objective

    objective = "fix the login bug in my portfoilo project and run all relevant tests"
    assert project_query_from_objective(objective) == "portfoilo"

    explicit = r'/code fix login in "D:\Projects\My Portfolio" and run tests'
    assert extract_windows_project_path(explicit) == r"D:\Projects\My Portfolio"
    assert project_query_from_objective(explicit) == "My Portfolio"


def test_coding_agent_project_ranking_fuzzy_matches_root_and_rejects_nested_artifact_repo():
    from iras.execution_router import rank_matching_project_candidates

    projects = [
        {
            "name": "Digital-Vertox",
            "path": r"D:\Projects\Digital-Vertox",
            "depth": 1,
            "git": True,
            "score": 50,
        },
        {
            "name": "mockup-sandbox",
            "path": r"D:\Projects\Portfolio\artifacts\mockup-sandbox",
            "depth": 3,
            "git": True,
            "score": 50,
        },
        {
            "name": "Portfolio",
            "path": r"D:\Projects\Portfolio",
            "depth": 1,
            "git": True,
            "score": 50,
        },
    ]
    ranked = rank_matching_project_candidates("portfoilo", projects)
    assert [item["name"] for item in ranked] == ["Portfolio"]


def test_coding_agent_project_ranking_detects_genuine_ambiguity():
    from iras.execution_router import project_candidates_are_ambiguous, rank_matching_project_candidates

    projects = [
        {"name": "Portfolio", "path": r"C:\Work\Portfolio", "depth": 1, "git": True, "score": 50},
        {"name": "Portfolio", "path": r"D:\Projects\Portfolio", "depth": 1, "git": True, "score": 50},
    ]
    ranked = rank_matching_project_candidates("Portfolio", projects)
    assert len(ranked) == 2
    assert project_candidates_are_ambiguous("Portfolio", ranked) is True


def test_coding_agent_command_parser_supports_project_and_run_controls():
    from iras.coding_agent import parse_coding_agent_command

    assert parse_coding_agent_command("/code projects") == ("projects", "")
    assert parse_coding_agent_command("/code use Portfolio") == ("use", "Portfolio")
    assert parse_coding_agent_command("/code pause run_123") == ("pause", "run_123")
    assert parse_coding_agent_command("/code resume") == ("resume", "")
    assert parse_coding_agent_command("/code diff") == ("diff", "")
    assert parse_coding_agent_command("/code fix the login bug") == ("run", "fix the login bug")


def test_cloud_coding_agent_exposes_project_selection_and_run_control_endpoints():
    cloud = Path("src/iras/cloud_api.py").read_text(encoding="utf-8")
    assert '@app.get("/v1/coding-agent/projects")' in cloud
    assert '@app.post("/v1/coding-agent/project")' in cloud
    assert '@app.post("/v1/coding-agent/runs/{run_id}/pause")' in cloud
    assert '@app.post("/v1/coding-agent/runs/{run_id}/resume")' in cloud
    assert '@app.post("/v1/coding-agent/runs/{run_id}/cancel")' in cloud
    assert '@app.get("/v1/coding-agent/runs/{run_id}/diff")' in cloud
    assert "force_project=True" in cloud
    assert "coding_agent_project:" in cloud
