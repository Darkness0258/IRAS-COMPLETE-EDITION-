from __future__ import annotations

from typing import Any
import re


# Narrow, engineering-focused tool surface. Actual authorization still happens
# in ToolRegistry + RemoteAccessPolicy + the Windows device executor.
CODING_AGENT_CORE_TOOLS = {
    "device_system_info",
    "device_find_projects",
    "device_list_files",
    "device_read_text",
    "device_read_text_range",
    "device_search_text",
    "device_file_info",
    "device_git_status",
    "device_git_diff",
    "device_git_log",
    "device_write_text",
    "device_replace_text",
    "device_make_directory",
    "device_run_tests",
    "device_quick_code",
    "device_quick_code_run_in_vscode",
}

# Windows interaction is available to the Coding Agent, but it is not an
# authorization bypass. READ/SAFE/SYSTEM/CRITICAL checks still apply normally.
CODING_AGENT_WINDOWS_TOOLS = {
    "device_computer_status",
    "device_open_project",
    "device_open_app",
    "device_app_control",
    "device_observe_ui",
    "device_semantic_action",
    "device_interact_app",
    "device_computer_observe",
    "device_computer_action",
    "device_computer_verify",
    "device_capture_screen",
    "device_screen_preview",
    "device_ui_find_text",
    "device_ui_click_text",
    "device_ui_type_text",
    "device_ui_wait_text",
    "device_verify_state",
    "device_clipboard_get",
    "device_clipboard_set",
    "device_list_processes",
    # Critical and shell=False. It only executes when the active Remote/local
    # policy permits CRITICAL command execution (for example bounded Master).
    "device_run_command",
}

CODING_AGENT_TOOL_ALLOWLIST = CODING_AGENT_CORE_TOOLS | CODING_AGENT_WINDOWS_TOOLS

CODING_AGENT_READ_TOOLS = {
    "device_computer_status",
    "device_system_info",
    "device_find_projects",
    "device_list_files",
    "device_read_text",
    "device_read_text_range",
    "device_search_text",
    "device_file_info",
    "device_git_status",
    "device_git_diff",
    "device_git_log",
    "device_observe_ui",
    "device_computer_observe",
    "device_computer_verify",
    "device_capture_screen",
    "device_screen_preview",
    "device_ui_find_text",
    "device_verify_state",
    "device_clipboard_get",
    "device_list_processes",
}

CODING_AGENT_TEST_TOOLS = CODING_AGENT_READ_TOOLS | {
    "device_run_tests",
    "device_open_project",
    "device_open_app",
    "device_app_control",
    # Useful for npm/gradle/cargo/build commands when the active policy permits
    # CRITICAL shell-safe command execution.
    "device_run_command",
}


def coding_agent_role_allowlist(role: str) -> set[str]:
    normalized = str(role or "").strip().lower()
    if normalized == "coder":
        return set(CODING_AGENT_TOOL_ALLOWLIST)
    if normalized == "tester":
        return set(CODING_AGENT_TEST_TOOLS)
    if normalized in {"reviewer", "researcher"}:
        return set(CODING_AGENT_READ_TOOLS)
    if normalized == "coordinator":
        return set()
    return set(CODING_AGENT_READ_TOOLS)

_CODING_VERB_RE = re.compile(
    r"\b(build|implement|develop|refactor|fix|debug|modify|edit|code|upgrade|integrate|migrate|test|repair)\b",
    re.IGNORECASE,
)
_CODING_CONTEXT_RE = re.compile(
    r"\b(project|repo(?:sitory)?|codebase|source|module|package|api|backend|frontend|app|application|website|python|javascript|typescript|java|rust|go|c\+\+|c#|git|pytest|tests?|IRAS)\b",
    re.IGNORECASE,
)


def is_coding_agent_objective(text: str) -> bool:
    cleaned = " ".join(str(text or "").strip().split())
    if not cleaned:
        return False
    lower = cleaned.lower()
    if lower.startswith("/code "):
        return True
    return bool(_CODING_VERB_RE.search(cleaned) and _CODING_CONTEXT_RE.search(cleaned))



def build_coding_agent_graph(objective: str) -> list[dict[str, Any]]:
    """Return a deterministic engineering DAG for the dedicated Coding Agent.

    The graph intentionally includes a repair pass after testing. The repair
    node runs even when testing failed; when tests already pass it is instructed
    to avoid gratuitous edits and simply confirm the implementation evidence.
    """
    goal = " ".join(str(objective or "").strip().split())
    if not goal:
        raise ValueError("Coding Agent objective is required.")

    return [
        {
            "id": "code-inspect",
            "title": "Inspect project and establish baseline",
            "prompt": (
                "Inspect the resolved project, git state, relevant source, and existing tests. "
                "Identify the smallest safe implementation plan for the objective. Do not edit yet. "
                "Record exact files and baseline evidence. Objective: " + goal
            ),
            "role": "reviewer",
            "priority": 95,
            "depends_on": [],
            "max_retries": 1,
        },
        {
            "id": "code-implement",
            "title": "Implement the requested change",
            "prompt": (
                "Implement the objective using the upstream inspection evidence. Prefer bounded file tools over GUI typing. "
                "You may use permissioned Windows controls to open/focus VS Code, inspect the UI, or operate the integrated terminal "
                "when that materially helps. Preserve unrelated behavior and report every changed file. Objective: " + goal
            ),
            "role": "coder",
            "priority": 90,
            "depends_on": ["code-inspect"],
            "max_retries": 2,
        },
        {
            "id": "code-test",
            "title": "Run targeted tests and diagnostics",
            "prompt": (
                "Run the strongest relevant bounded tests/build/diagnostics for the implementation. "
                "Inspect failures precisely and provide reproducible evidence. Objective: " + goal
            ),
            "role": "tester",
            "priority": 85,
            "depends_on": ["code-implement"],
            "max_retries": 1,
        },
        {
            "id": "code-repair",
            "title": "Repair failures or confirm clean implementation",
            "prompt": (
                "Use the implementation and test output as evidence. If tests failed or the objective is incomplete, diagnose and repair "
                "the smallest relevant cause, then inspect the resulting diff. If tests already passed and the objective is satisfied, make "
                "no unnecessary edits; only verify the current change. Permissioned Windows/VS Code controls are available when needed. "
                "Objective: " + goal
            ),
            "role": "coder",
            "priority": 82,
            "depends_on": ["code-test"],
            "max_retries": 2,
            "continue_on_failure": True,
        },
        {
            "id": "code-final-test",
            "title": "Run final verification",
            "prompt": (
                "Run final relevant tests/build checks against the repaired/current implementation, inspect git status/diff, and determine "
                "whether the requested objective is actually complete. Do not claim success without concrete evidence. Objective: " + goal
            ),
            "role": "tester",
            "priority": 80,
            "depends_on": ["code-repair"],
            "max_retries": 1,
            "continue_on_failure": True,
        },
        {
            "id": "code-review",
            "title": "Review implementation and regression risk",
            "prompt": (
                "Review the final diff, test evidence, correctness, security, maintainability, and regression risk. "
                "Call out any unresolved blocker explicitly. Objective: " + goal
            ),
            "role": "reviewer",
            "priority": 75,
            "depends_on": ["code-final-test"],
            "max_retries": 1,
            "continue_on_failure": True,
        },
    ]


def coding_agent_status() -> dict[str, Any]:
    return {
        "enabled": True,
        "mode": "dedicated_engineering_agent",
        "workflow": [
            "inspect",
            "implement",
            "test",
            "repair_if_needed",
            "final_test",
            "review",
            "coordinate",
        ],
        "windows_control": {
            "enabled": True,
            "permissioned": True,
            "tools": sorted(CODING_AGENT_WINDOWS_TOOLS),
            "notes": (
                "Windows actions remain subject to ToolRegistry permissions, Remote session level, local Remote policy, "
                "bridge filesystem roots, emergency stop, and Windows/UAC boundaries. device_run_command is CRITICAL and shell=False."
            ),
        },
        "core_tools": sorted(CODING_AGENT_CORE_TOOLS),
    }
