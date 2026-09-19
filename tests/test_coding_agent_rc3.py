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
