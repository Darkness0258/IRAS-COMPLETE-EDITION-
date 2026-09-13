from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from iras.device_bridge.skills import (
    LearnedStep,
    PersistentSkillStore,
)


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
    "device_skill_delete",
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
    "device_skill_find",
    "device_skill_validate",
    "device_skill_list",
    "device_skill_inspect",
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


def _result_output(payload: dict[str, Any]) -> dict[str, Any]:
    output = payload.get("output")
    return output if isinstance(output, dict) else {}


def _expected_state(output: dict[str, Any]) -> dict[str, Any]:
    observation = output.get("verification_observation")
    if not isinstance(observation, dict):
        return {}
    # Keep only compact semantic evidence. Coordinates/screenshot geometry are
    # intentionally never copied into persistent skills.
    expected: dict[str, Any] = {"verified": True}
    for key in ("window_name", "title", "element_count", "screenshot_hash"):
        if key in observation:
            expected[key] = observation[key]
    visible_names: list[str] = []
    elements = observation.get("elements")
    if isinstance(elements, list):
        for element in elements:
            if not isinstance(element, dict):
                continue
            name = str(element.get("name") or "").strip()
            if name and name not in visible_names:
                visible_names.append(name)
            if len(visible_names) >= 8:
                break
    if visible_names:
        expected["visible_names"] = visible_names
    return expected


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
    learnable_steps: list[LearnedStep] = field(default_factory=list)
    active_skill_id: str = ""
    learned_skill_id: str = ""
    learning_blocked: bool = False
    learning_block_reason: str = ""
    learning_recovery_pending: bool = False
    skill_store: PersistentSkillStore = field(default_factory=PersistentSkillStore)
    _learning_finalized: bool = False

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

    def _capture_skill_lookup(self, output: dict[str, Any]) -> None:
        match = output.get("match")
        if isinstance(match, dict):
            self.active_skill_id = str(match.get("skill_id") or "")

    def _capture_verified_semantic_step(
        self,
        arguments: dict[str, Any],
        output: dict[str, Any],
    ) -> None:
        observation = output.get("verification_observation")
        if not isinstance(observation, dict):
            return
        app = str(arguments.get("app") or "").strip()
        action = str(arguments.get("action") or "").strip()
        target = str(arguments.get("target") or "").strip()
        role = str(arguments.get("role") or "").strip()
        if not app or not action or not target:
            return

        # v3.2 returns the exact selected UI Automation element. Persist only
        # its semantic identity fields; explicitly ignore rect/derived_click.
        selected = output.get("selected_element")
        if not isinstance(selected, dict):
            selected = {}
        locator = {
            "name": str(selected.get("name") or target),
            "automation_id": str(selected.get("automation_id") or ""),
            "role": str(selected.get("role") or role),
            "occurrence": max(1, int(arguments.get("occurrence", 1) or 1)),
        }
        step = LearnedStep(
            app=app,
            action=action,
            locator=locator,
            text=str(arguments.get("text") or ""),
            key=str(arguments.get("key") or ""),
            replace=bool(arguments.get("replace", False)),
            expected_state=_expected_state(output),
        )
        if step.is_safe():
            self.learnable_steps.append(step)

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
            self.last_error = str(payload.get("error") or "Unknown tool failure.")
            if self.active_skill_id and name == "device_semantic_action":
                self.skill_store.record_failure(self.active_skill_id)
                self.learning_recovery_pending = True
            return

        output = _result_output(payload)

        if (
            name in STATE_CHANGING_DEVICE_TOOLS
            and name not in {
                "device_open_app",
                "device_app_control",
                "device_semantic_action",
            }
        ):
            self.learning_blocked = True
            self.learning_block_reason = (
                "workflow used a state-changing action that is not a "
                "verified semantic UI step"
            )

        if name == "device_skill_find":
            self._capture_skill_lookup(output)

        if name == "device_skill_validate" and output.get("valid") is False:
            self.learning_recovery_pending = True

        if name == "device_observe_ui":
            self.needs_verification = False
            return

        if name == "device_semantic_action":
            verified = bool(output.get("verification_observation"))
            self.needs_verification = not verified
            if verified:
                self._capture_verified_semantic_step(arguments, output)
                self.learning_recovery_pending = False
            return

        if name == "device_open_app":
            self.needs_verification = not bool(
                output.get("launch_verified") is True
                or output.get("foreground_verified") is True
            )
            return

        if name in {"device_interact_app", "device_app_control"}:
            self.needs_verification = True
            return

        if name in READ_VERIFY_TOOLS:
            # Skill validation/listing is read-only. It must not erase a
            # pending verification caused by a previous state change unless a
            # real UI observation was explicitly requested.
            if name not in {
                "device_skill_find",
                "device_skill_validate",
                "device_skill_list",
                "device_skill_inspect",
            }:
                self.needs_verification = False
            return

        if name in STATE_CHANGING_DEVICE_TOOLS:
            verified = (
                output.get("verified")
                or output.get("verified_state")
                or output.get("verified_playback")
            )
            self.needs_verification = verified is False

    def _finalize_learning(self) -> None:
        if self._learning_finalized:
            return
        self._learning_finalized = True

        # A v3.4 learned app skill is intentionally single-app and contains
        # only verified semantic UI actions. Raw-coordinate interactions and
        # shell/admin actions are therefore never serialized into the store.
        if (
            not self.learnable_steps
            or self.needs_verification
            or self.learning_blocked
            or self.learning_recovery_pending
            or self.consecutive_failures > 0
        ):
            return

        apps = {step.app.casefold().strip() for step in self.learnable_steps}
        if len(apps) != 1:
            return

        active = (
            self.skill_store.get(self.active_skill_id)
            if self.active_skill_id
            else None
        )
        if active is not None:
            if active.parameters:
                # Preserve parameter placeholders learned/defined for this
                # reusable skill. Concrete values from this execution must not
                # collapse it into a one-contact/one-message trace.
                skill = active
            else:
                skill = self.skill_store.learn_verified(
                    active.intent_template,
                    self.learnable_steps,
                    parameters=active.parameters,
                )
            self.skill_store.record_success(active.skill_id)
        else:
            skill = self.skill_store.learn_verified(
                self.goal,
                self.learnable_steps,
            )

        if skill:
            self.learned_skill_id = skill.skill_id

    def after_result_nudge(self, payload: dict[str, Any]) -> str:
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

    def empty_final_response(self) -> str:
        # Evidence-aware fallback when the model returns no final text.
        if self.needs_verification:
            return (
                "I executed part of that device workflow, but the final "
                "state is still unverified, so I won't claim it succeeded."
            )

        if self.consecutive_failures > 0:
            detail = (
                f" Last error: {self.last_error}"
                if self.last_error
                else ""
            )
            return (
                "The device workflow did not finish cleanly, so I won't "
                "claim success." + detail
            )

        if self.successful_calls > 0:
            return (
                "The device workflow completed verified tool steps, but the "
                "model returned no final message. I won't claim anything "
                "beyond the verified tool evidence."
            )

        return (
            "I couldn't complete that device workflow, and I won't claim "
            "that it succeeded."
        )

    def finalization_nudge(self) -> str:
        if self.needs_verification:
            return (
                "The last state-changing action is not verified yet. Do not "
                "finish with a success claim. Use an observation/read/status "
                "tool now to verify the requested end state."
            )

        if self.consecutive_failures > 0 and self.successful_calls == 0:
            return (
                "The task has not produced a successful tool result yet. Try "
                "a different safe approach or explain the concrete blocking "
                "capability instead of claiming completion."
            )

        self._finalize_learning()
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
            "active_skill_id": self.active_skill_id or None,
            "learned_skill_id": self.learned_skill_id or None,
            "learned_step_count": len(self.learnable_steps),
            "learning_blocked": self.learning_blocked,
            "learning_block_reason": self.learning_block_reason or None,
            "learning_recovery_pending": self.learning_recovery_pending,
        }


def workflow_system_nudge(user_text: str) -> str:
    return (
        "AUTONOMOUS WORKFLOW MODE: Treat the user's request as one goal, not "
        "as isolated commands. Privately maintain a small plan and execute it "
        "step by step using only the supplied bounded tools. Do not reveal "
        "hidden chain-of-thought or a private plan. Use this loop: PLAN the "
        "next smallest safe step -> EXECUTE -> INSPECT real results -> VERIFY "
        "state -> ADAPT/RECOVER -> FINISH only when tool evidence supports the "
        "requested outcome. For app GUI work, check device_skill_find first. "
        "If a learned skill matches, validate each learned step with "
        "device_skill_validate before execution, then execute only through the "
        "existing permissioned device_semantic_action tool. If validation says "
        "a target is stale, use the returned live v3.2 observation to recover "
        "semantically; never use a memorized or invented coordinate. For "
        "unfamiliar GUI state, observe first. After navigation, typing, "
        "clicking, opening an unverified app, or another uncertain state "
        "change, verify before claiming completion. Never repeat the same "
        "failed call over and over; re-observe and change approach. Prefer "
        "specialized tools over generic UI actions. Stay inside current-turn "
        "app/device scope and the existing permission system. Learned skills "
        "are hints, never permission bypasses. If bounded tools cannot complete "
        "the goal, state the missing capability instead of fabricating success. "
        "Current user goal: "
        f"{user_text}"
    )
