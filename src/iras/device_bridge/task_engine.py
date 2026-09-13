from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any


STATE_CHANGING_DEVICE_TOOLS = {
    "device_open_app",
    "device_app_control",
    "device_interact_app",
    "device_semantic_action",
    "device_spotify_play",
    "device_media_control",
    "device_open_url",
    "device_open_project",
    "device_run_tests",
}

READ_VERIFY_TOOLS = {
    "device_observe_ui",
    "device_capture_screen",
    "device_detect_apps",
    "device_list",
    "device_system_info",
    "device_list_files",
    "device_read_text",
    "device_git_status",
}

MAX_REPEAT_CALLS = 2
MAX_CONSECUTIVE_FAILURES = 3


def planner_step_budget(base_steps: int) -> int:
    base = max(1, int(base_steps))
    return min(max(base, 12), 16)


def stable_call_signature(
    name: str,
    arguments: dict[str, Any],
) -> str:
    return (
        str(name)
        + ":"
        + json.dumps(
            arguments or {},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    )


def _result_output(
    payload: dict[str, Any],
) -> dict[str, Any]:
    output = payload.get("output")
    return output if isinstance(output, dict) else {}


@dataclass
class TaskTracker:
    goal: str
    call_counts: dict[str, int] = field(default_factory=dict)
    call_results: dict[str, bool] = field(default_factory=dict)
    successful_calls: int = 0
    failed_calls: int = 0
    consecutive_failures: int = 0
    needs_verification: bool = False
    last_tool: str = ""
    last_error: str = ""

    def before_call(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> tuple[bool, str]:
        signature = stable_call_signature(name, arguments)
        count = self.call_counts.get(signature, 0)
        previous_failed = self.call_results.get(signature) is False

        if previous_failed and count >= MAX_REPEAT_CALLS:
            return (
                False,
                (
                    "Blocked an unchanged repeated tool call after it already "
                    "failed twice. Re-observe/re-diagnose and use a different "
                    "safe approach instead."
                ),
            )

        self.call_counts[signature] = count + 1
        return (True, "")

    def record(
        self,
        name: str,
        arguments: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        signature = stable_call_signature(name, arguments)
        ok = bool(payload.get("ok"))
        self.call_results[signature] = ok
        self.last_tool = str(name)

        if ok:
            self.successful_calls += 1
            self.consecutive_failures = 0
            self.last_error = ""
        else:
            self.failed_calls += 1
            self.consecutive_failures += 1
            self.last_error = str(
                payload.get("error")
                or "Unknown tool failure."
            )
            return

        output = _result_output(payload)

        if name == "device_observe_ui":
            self.needs_verification = False
            return

        if name == "device_semantic_action":
            self.needs_verification = not bool(
                output.get("verification_observation")
            )
            return

        if name == "device_open_app":
            self.needs_verification = not bool(
                output.get("launch_verified") is True
                or output.get("foreground_verified") is True
            )
            return

        if name in {
            "device_interact_app",
            "device_app_control",
        }:
            self.needs_verification = True
            return

        if name in READ_VERIFY_TOOLS:
            self.needs_verification = False
            return

        if name in STATE_CHANGING_DEVICE_TOOLS:
            verified = (
                output.get("verified")
                or output.get("verified_state")
                or output.get("verified_playback")
            )
            self.needs_verification = verified is False

    def after_result_nudge(
        self,
        payload: dict[str, Any],
    ) -> str:
        if not payload.get("ok"):
            if self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                return (
                    "WORKFLOW RECOVERY: three consecutive tool steps failed. "
                    "Do not keep repeating the same route. Re-observe or "
                    "re-diagnose, choose a different safe tool/target, or state "
                    "the missing capability if no safe alternative exists."
                )

            return (
                "WORKFLOW RECOVERY: the previous tool step failed. Inspect the "
                "real error and current state before choosing the next action. "
                "Do not claim success and do not repeat the identical failed "
                "call unchanged."
            )

        if self.needs_verification:
            return (
                "WORKFLOW VERIFY: the previous action was accepted but the "
                "desired end state is not yet verified. Before finalizing, use "
                "an appropriate observation/read/status tool to confirm it."
            )

        return (
            "WORKFLOW CONTINUE: use the real result above to decide whether "
            "the user's goal is complete. If not, perform the next smallest "
            "safe step. If complete, give a concise truthful result."
        )

    def finalization_nudge(self) -> str:
        if self.needs_verification:
            return (
                "The last state-changing action is not verified yet. Do not "
                "finish with a success claim. Use an observation/read/status "
                "tool now to verify the requested end state."
            )

        if (
            self.consecutive_failures > 0
            and self.successful_calls == 0
        ):
            return (
                "The task has not produced a successful tool result yet. Try "
                "a different safe approach or explain the concrete blocking "
                "capability instead of claiming completion."
            )

        return ""

    def audit_summary(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "consecutive_failures": self.consecutive_failures,
            "needs_verification": self.needs_verification,
            "last_tool": self.last_tool,
            "last_error": self.last_error or None,
        }


def workflow_system_nudge(user_text: str) -> str:
    return (
        "AUTONOMOUS WORKFLOW MODE: Treat the user's request as one goal, not "
        "as isolated commands. Privately maintain a small plan and execute it "
        "step by step using only the supplied bounded tools. Do not reveal "
        "hidden chain-of-thought or a private plan. Use this loop: PLAN the "
        "next smallest safe step -> EXECUTE -> INSPECT real results -> VERIFY "
        "state -> ADAPT/RECOVER -> FINISH only when tool evidence supports the "
        "requested outcome. For unfamiliar GUI state, observe first. After "
        "navigation, typing, clicking, opening an unverified app, or another "
        "uncertain state change, verify before claiming completion. Never "
        "repeat the same failed call over and over; re-observe and change "
        "approach. Prefer specialized tools over generic UI actions. Stay "
        "inside current-turn app/device scope and the existing permission "
        "system. If bounded tools cannot complete the goal, state the missing "
        "capability instead of fabricating success. Current user goal: "
        f"{user_text}"
    )
