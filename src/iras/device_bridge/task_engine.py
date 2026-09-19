from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

from iras.device_bridge.skills import (
    LearnedStep,
    PersistentSkillStore,
)
from iras.device_bridge.workflow_memory import CrossAppWorkflowMemory
from iras.master_control import active_master_execution_limits


STATE_CHANGING_DEVICE_TOOLS = {
    "device_open_app",
    "device_app_control",
    "device_interact_app",
    "device_semantic_action",
    "device_computer_action",
    "device_whatsapp_open_chat",
    "device_spotify_play",
    "device_media_control",
    "device_open_url",
    "device_open_project",
    "device_run_tests",
    "device_skill_delete",
}

READ_VERIFY_TOOLS = {
    "device_observe_ui",
    "device_computer_status",
    "device_computer_observe",
    "device_computer_verify",
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


def _normalize_goal_text(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _compound_goal(value: str) -> bool:
    normalized = " " + _normalize_goal_text(value) + " "
    return any(marker in normalized for marker in (" and ", " then ", " after that "))


def _terminal_goal_target(value: str) -> str:
    normalized = _normalize_goal_text(value)
    match = re.search(
        r"(?:\band\b|\bthen\b|\bafter that\b)\s+"
        r"(?:open|click|select|choose|press|go to|navigate to)\s+"
        r"(.+?)\s*[.!?]*$",
        normalized, flags=re.IGNORECASE,
    )
    if not match:
        return ""
    target = match.group(1).strip(" .!?")
    return re.sub(r"\s+(?:in|inside|on)\s+[a-z0-9 .+_-]+$", "", target, flags=re.IGNORECASE).strip()


def _semantic_target_matches(actual: str, expected: str) -> bool:
    left, right = _normalize_goal_text(actual), _normalize_goal_text(expected)
    if not left or not right:
        return False
    return left == right or left.endswith(" " + right) or right.endswith(" " + left)


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
    goal_checkpoint_required: bool = False
    last_semantic_target: str = ""
    accessibility_limited: bool = False
    accessibility_reason: str = ""
    last_outcome_decision: str = ""
    outcome_retry_count: int = 0
    outcome_retry_budget_remaining: int = 0
    outcome_recovery_required: bool = False
    outcome_goal_sufficient: bool = False
    automatic_recovery_steps: int = 0
    last_automatic_recovery_decision: str = ""
    last_automatic_recovery_ok: bool | None = None
    last_automatic_recovery_observation_id: str = ""
    last_automatic_recovery_route: str = ""
    last_automatic_recovery_next_step: str = ""
    automatic_action_replay_allowed: bool = False
    recovery_fresh_plan_pending: bool = False
    recovery_fresh_observation_id: str = ""
    recovery_fresh_element_ids: list[str] = field(default_factory=list)
    recovery_fresh_plan: dict[str, Any] = field(default_factory=dict)
    fresh_action_binding_validated: bool = False
    chained_verification_pending: bool = False
    chained_verification_call: dict[str, Any] = field(default_factory=dict)
    recovery_route_history: list[dict[str, Any]] = field(default_factory=list)
    recovery_performance_store: Any | None = None
    recovery_learning_pending_route: str = ""
    recovery_learning_pending_context: dict[str, Any] = field(default_factory=dict)
    material_replan_required: bool = False
    material_replan_contract: dict[str, Any] = field(default_factory=dict)
    recovery_loop_terminated: bool = False
    recovery_loop_block_reason: str = ""
    workflow_memory: CrossAppWorkflowMemory = field(default_factory=CrossAppWorkflowMemory)
    workflow_memory_last_emitted_revision: int = 0
    skill_store: PersistentSkillStore = field(default_factory=PersistentSkillStore)
    _learning_finalized: bool = False

    def before_call(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> tuple[bool, str]:
        # v3.5.17: once an exhausted recovery route forces a material replan,
        # the controller rejects the exact exhausted tool+argument route. The
        # model may still inspect state or choose another safe strategy.
        if self.material_replan_required:
            from iras.device_bridge.replan_guard import tool_call_signature

            signature = tool_call_signature(name, arguments)
            forbidden = {
                str(value)
                for value in (
                    self.material_replan_contract.get("forbidden_tool_signatures") or []
                )
            }
            if signature in forbidden:
                return (
                    False,
                    "Blocked exhausted recovery route: a materially different plan is required.",
                )

        # v3.5.15: after automatic recovery, a universal computer action must
        # bind to the fresh recovery observation. Stale observation/element ids
        # are rejected before the tool can receive input.
        if self.recovery_fresh_plan_pending and name == "device_computer_action":
            from iras.device_bridge.fresh_action_execution import (
                build_chained_verification_call,
                validate_fresh_plan_execution,
            )

            allowed, reason = validate_fresh_plan_execution(
                self.recovery_fresh_plan,
                name,
                arguments,
            )
            if not allowed:
                return (False, f"Blocked fresh post-recovery action: {reason}.")
            self.fresh_action_binding_validated = True
            self.chained_verification_call = (
                build_chained_verification_call(self.recovery_fresh_plan) or {}
            )

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

    def can_run_automatic_recovery(self) -> bool:
        # Keep the recovery-step budget defined in one place. Import lazily to
        # avoid coupling the task tracker to recovery route selection at module load.
        from iras.device_bridge.recovery_runtime import MAX_AUTOMATIC_RECOVERY_STEPS

        limit = MAX_AUTOMATIC_RECOVERY_STEPS
        master_limits = active_master_execution_limits()
        if master_limits.get("active"):
            limit = max(limit, int(master_limits.get("recovery_attempts") or 24))
        return self.automatic_recovery_steps < limit

    def automatic_recovery_guard(self, directive: dict[str, Any]) -> dict[str, Any]:
        from iras.device_bridge.replan_guard import recovery_route_cycle_guard

        if not self.can_run_automatic_recovery():
            return {
                "allowed": False,
                "reason": "automatic_recovery_budget_exhausted",
                "requires_materially_different_plan": True,
                "action_replay_allowed": False,
            }
        return recovery_route_cycle_guard(self.recovery_route_history, directive)

    def can_execute_automatic_recovery(self, directive: dict[str, Any]) -> bool:
        return bool(self.automatic_recovery_guard(directive).get("allowed"))

    def require_material_replan(
        self,
        *,
        directive: dict[str, Any] | None = None,
        reason_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        from iras.device_bridge.replan_guard import material_replan_contract

        contract = material_replan_contract(
            self.recovery_route_history,
            blocked_directive=directive,
            reason_codes=reason_codes,
        )
        self.material_replan_required = True
        self.material_replan_contract = contract
        self.recovery_loop_terminated = True
        self.recovery_loop_block_reason = str(
            (reason_codes or ["materially_different_plan_required"])[0]
        )
        return contract

    def recovery_planner_constraints(self) -> dict[str, Any]:
        """Return v3.5.18 history-aware constraints for the next planner turn."""
        from iras.device_bridge.replan_guard import recovery_history_planner_constraints

        contract = self.material_replan_contract if self.material_replan_required else {}
        constraints = recovery_history_planner_constraints(
            self.recovery_route_history,
            exhausted_routes=list(contract.get("exhausted_routes") or []),
            forbidden_tool_signatures=list(
                contract.get("forbidden_tool_signatures") or []
            ),
        )
        if self.recovery_performance_store is not None:
            try:
                priors = self.recovery_performance_store.snapshot()
            except Exception:
                priors = {}
            try:
                context_priors = self.recovery_performance_store.context_snapshot()
            except Exception:
                context_priors = {}
            if isinstance(priors, dict):
                constraints["learned_route_priors"] = priors
                constraints["learned_route_priors_version"] = "3.6.0"
            if isinstance(context_priors, dict):
                constraints["learned_context_route_priors"] = context_priors
                constraints["learned_context_route_priors_version"] = "3.6.0"
        return constraints

    def recovery_planner_message(self) -> str:
        from iras.device_bridge.replan_guard import recovery_history_planner_message

        return recovery_history_planner_message(self.recovery_planner_constraints())

    def record_automatic_recovery(
        self,
        directive: dict[str, Any],
        payload: dict[str, Any],
        *,
        handoff: dict[str, Any] | None = None,
        fresh_plan: dict[str, Any] | None = None,
    ) -> None:
        """Record controller-driven read-only recovery without clearing verification.

        A recovery observation is evidence for the next decision, not proof that
        the user's semantic goal is complete, so ``needs_verification`` remains
        unchanged.
        """

        self.automatic_recovery_steps += 1
        from iras.device_bridge.replan_guard import (
            recovery_route_signature,
            tool_call_signature,
        )

        route_entry = {
            "route": str(directive.get("route") or ""),
            "route_signature": recovery_route_signature(directive),
            "tool": str(directive.get("tool") or ""),
            "tool_signature": tool_call_signature(
                str(directive.get("tool") or ""),
                directive.get("arguments") if isinstance(directive.get("arguments"), dict) else {},
            ),
            "automatic_step": self.automatic_recovery_steps,
            "ok": bool(payload.get("ok")),
        }
        self.recovery_route_history.append(route_entry)
        # v3.5.20 credits/blames a recovery route only after the next semantic
        # verification result is known. A successful observation alone is not
        # treated as proof that the route solved the user's goal.
        if bool(payload.get("ok")):
            self.recovery_learning_pending_route = str(directive.get("route") or "")
            raw_context = directive.get("learning_context")
            self.recovery_learning_pending_context = (
                dict(raw_context) if isinstance(raw_context, dict) else {}
            )
        self.last_automatic_recovery_decision = str(
            directive.get("decision") or ""
        ).upper()
        self.last_automatic_recovery_ok = bool(payload.get("ok"))
        output = payload.get("output")
        if isinstance(output, dict):
            self.last_automatic_recovery_observation_id = str(
                output.get("observation_id") or ""
            )
        self.last_automatic_recovery_route = str(directive.get("route") or "")
        handoff = handoff if isinstance(handoff, dict) else {}
        self.last_automatic_recovery_next_step = str(handoff.get("next_step") or "")
        self.recovery_fresh_observation_id = str(handoff.get("fresh_observation_id") or "")
        grounded = handoff.get("grounded_elements")
        self.recovery_fresh_element_ids = [
            str(item.get("element_id") or "")
            for item in grounded
            if isinstance(item, dict) and str(item.get("element_id") or "")
        ] if isinstance(grounded, list) else []
        self.recovery_fresh_plan_pending = bool(
            handoff.get("fresh_state_available") and self.recovery_fresh_observation_id
        )
        if isinstance(fresh_plan, dict):
            self.recovery_fresh_plan = fresh_plan
        else:
            from iras.device_bridge.fresh_action_planning import build_fresh_action_plan
            self.recovery_fresh_plan = build_fresh_action_plan(handoff)
        self.fresh_action_binding_validated = False
        self.chained_verification_pending = False
        self.chained_verification_call = {}
        # v3.5.15 never grants the controller permission to replay the action
        # that failed verification. A new action must be planned from fresh state.
        self.automatic_action_replay_allowed = False

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
        # v3.6.0 session-scoped cross-app workflow memory. Only successful
        # tool results are captured; semantic facts enter memory only after
        # verification proves them. This memory never grants tool permission.
        try:
            self.workflow_memory.capture_tool_result(name, arguments, output)
        except Exception:
            pass

        if self.material_replan_required and ok:
            from iras.device_bridge.replan_guard import tool_call_signature

            replan_tools = {
                "device_computer_observe",
                "device_observe_ui",
                "device_app_control",
                "device_open_app",
                "device_semantic_action",
                "device_computer_action",
            }
            if name in replan_tools:
                signature = tool_call_signature(name, arguments)
                forbidden = {
                    str(value)
                    for value in (
                        self.material_replan_contract.get("forbidden_tool_signatures") or []
                    )
                }
                if signature not in forbidden:
                    self.material_replan_required = False
                    self.material_replan_contract = {}
                    self.recovery_loop_terminated = False
                    self.recovery_loop_block_reason = ""

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
            accessibility = output.get("accessibility_available")
            self.accessibility_limited = accessibility is False
            self.accessibility_reason = str(output.get("accessibility_reason") or "")
            if self.accessibility_limited:
                self.goal_checkpoint_required = False
            elif _compound_goal(self.goal):
                terminal = _terminal_goal_target(self.goal)
                self.goal_checkpoint_required = bool(
                    terminal and self.last_semantic_target and
                    not _semantic_target_matches(self.last_semantic_target, terminal)
                )
            else:
                self.goal_checkpoint_required = False
            return

        if name == "device_computer_observe":
            self.needs_verification = False
            uia_actionable = output.get("uia_actionable") is True
            vision_available = output.get("vision_available") is True
            observation_scope = str(output.get("observation_scope") or "auto").lower()
            if observation_scope == "desktop":
                # UIA describes only the foreground application. Desktop-wide
                # grounding therefore requires the visual backend.
                self.accessibility_limited = not vision_available
            else:
                self.accessibility_limited = not (uia_actionable or vision_available)
            self.accessibility_reason = (
                "Neither Windows UI Automation nor configured visual grounding "
                "returned actionable controls for the current desktop."
                if self.accessibility_limited
                else ""
            )
            return

        if name == "device_computer_action":
            # A validated fresh post-recovery action consumes the binding but
            # immediately arms the read-only verification chain.
            self.chained_verification_pending = bool(
                self.fresh_action_binding_validated and self.chained_verification_call
            )
            self.recovery_fresh_plan_pending = False
            self.recovery_fresh_observation_id = ""
            self.recovery_fresh_element_ids = []
            self.recovery_fresh_plan = {}
            self.fresh_action_binding_validated = False
            # Fresh post-action observation proves input delivery only. The
            # user's desired end state still requires device_computer_verify.
            self.needs_verification = True
            self.learning_blocked = True
            self.learning_block_reason = (
                "workflow used universal visual/keyboard computer control; "
                "v3.7 does not persist raw visual action traces as learned skills"
            )
            return

        if name == "device_computer_verify":
            self.chained_verification_pending = False
            self.chained_verification_call = {}
            status = str(output.get("status") or "").upper()
            decision = output.get("decision")
            if not isinstance(decision, dict):
                decision = {}
            action = str(decision.get("action") or "").upper()
            self.last_outcome_decision = action
            self.outcome_retry_count = int(decision.get("failure_count") or 0)
            self.outcome_retry_budget_remaining = int(
                decision.get("retry_budget_remaining") or 0
            )
            self.outcome_recovery_required = action == "RECOVER"
            self.outcome_goal_sufficient = bool(decision.get("goal_sufficient"))

            # v3.5.20 route learning is tied to semantic verification, not merely
            # to whether the read-only recovery observation tool returned.
            learned_route = self.recovery_learning_pending_route
            if learned_route and self.recovery_performance_store is not None:
                semantic_verified = bool(
                    output.get("semantic_goal_verified")
                    or (action == "ACCEPT" and self.outcome_goal_sufficient)
                )
                try:
                    self.recovery_performance_store.record(
                        learned_route,
                        success=semantic_verified,
                        context=self.recovery_learning_pending_context,
                    )
                except Exception:
                    pass
                self.recovery_learning_pending_route = ""
                self.recovery_learning_pending_context = {}

            if action == "ACCEPT":
                # A state-only predicate may be true without proving the user's
                # semantic end goal. Keep verification pending in that case.
                self.needs_verification = not self.outcome_goal_sufficient
            elif action in {"RETRY", "ESCALATE_VISION", "RECOVER"}:
                self.needs_verification = True
            else:
                self.needs_verification = status != "PASS"
            return

        if name == "device_semantic_action":
            observation = output.get("verification_observation")
            verified = bool(observation)
            self.needs_verification = not verified
            if verified:
                self._capture_verified_semantic_step(arguments, output)
                self.learning_recovery_pending = False
                self.last_semantic_target = str(arguments.get("target") or "").strip()
                if isinstance(observation, dict):
                    accessibility = observation.get("accessibility_available")
                    self.accessibility_limited = accessibility is False
                    self.accessibility_reason = str(observation.get("accessibility_reason") or "")
                self.goal_checkpoint_required = _compound_goal(self.goal) and not self.accessibility_limited
            return

        if name == "device_open_app":
            self.needs_verification = not bool(
                output.get("launch_verified") is True
                or output.get("foreground_verified") is True
            )
            return

        if name == "device_app_control":
            self.needs_verification = output.get("verified_state") is not True
            return

        if name == "device_interact_app":
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
            or self.goal_checkpoint_required
            or self.accessibility_limited
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

    def workflow_memory_message_if_changed(self) -> str:
        revision = int(getattr(self.workflow_memory, "revision", 0) or 0)
        if revision <= self.workflow_memory_last_emitted_revision:
            return ""
        self.workflow_memory_last_emitted_revision = revision
        return self.workflow_memory.planner_message()

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

        if self.last_tool == "device_computer_verify":
            if self.last_outcome_decision == "RECOVER":
                return (
                    "WORKFLOW OUTCOME RECOVERY: verification exhausted its bounded "
                    "retry budget. Re-observe the live UI, re-ground the intended "
                    "target, and choose a different safe route instead of repeating "
                    "the same action."
                )
            if self.last_outcome_decision == "RETRY":
                return (
                    "WORKFLOW OUTCOME RETRY: the requested outcome is still not "
                    "verified. Retry only after a fresh observation/re-grounding; "
                    f"remaining bounded retry budget: {self.outcome_retry_budget_remaining}."
                )
            if self.last_outcome_decision == "ESCALATE_VISION":
                return (
                    "WORKFLOW OUTCOME ESCALATION: semantic evidence is insufficient. "
                    "Run visual grounding/verification before retrying the action."
                )
            if self.last_outcome_decision == "ACCEPT" and not self.outcome_goal_sufficient:
                return (
                    "WORKFLOW OUTCOME PARTIAL: the requested verification predicate "
                    "passed, but it is state-only evidence and does not prove the "
                    "semantic user goal. Verify the semantic end state before finishing."
                )

        if self.needs_verification:
            return (
                "WORKFLOW VERIFY: the previous action was accepted but the "
                "desired end state is not yet verified. Before finalizing, use "
                "an appropriate observation/read/status tool to confirm it."
            )

        if self.last_tool == "device_observe_ui" and self.accessibility_limited:
            return (
                "WORKFLOW ACCESSIBILITY LIMIT: Windows UI Automation returned "
                "no usable semantic controls. This does NOT mean the visual "
                "interface is blank. In v3.7, call device_computer_observe; local "
                "OmniParser will auto-start on demand when configured/discoverable and "
                "can ground visual-only controls into the fresh scene graph. "
                "Never invent coordinates."
            )

        if self.last_tool == "device_computer_action":
            return (
                "WORKFLOW OUTCOME CHECK: the universal computer action was "
                "injected, but the user's requested state is not yet proven. "
                "Call device_computer_verify with a semantic condition. PASS "
                "means the outcome is supported; FAIL means adapt/recover; "
                "INCONCLUSIVE is not success."
            )

        if self.goal_checkpoint_required:
            terminal = _terminal_goal_target(self.goal)
            suffix = (
                " The compound goal's terminal semantic target is " + repr(terminal) +
                ", and the last verified semantic action targeted " + repr(self.last_semantic_target) + "."
                if terminal else ""
            )
            return (
                "WORKFLOW GOAL CHECKPOINT: a verified semantic action proves only that specific UI interaction, not that the user's whole goal is complete. "
                "Call device_observe_ui now and compare the fresh semantic state with the original request. If a requested destination/control is still pending, continue with the next semantic action instead of finalizing." + suffix
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

        if self.accessibility_limited:
            detail = (" " + self.accessibility_reason) if self.accessibility_reason else ""
            return (
                "The app window is open, but Windows accessibility exposed no usable semantic controls. That does not mean the interface is visually blank. "
                "I won't invent coordinates or claim the remaining UI work succeeded." + detail
            )

        if self.goal_checkpoint_required:
            return (
                "The workflow made partial UI progress, but the requested compound end state has not passed a fresh semantic checkpoint, "
                "so I won't claim the whole goal is complete."
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
                "The device workflow made verified step-level progress, but the model returned no final message and I do not have enough "
                "goal-level evidence to claim the requested outcome is complete."
            )

        return (
            "I couldn't complete that device workflow, and I won't claim "
            "that it succeeded."
        )

    def finalization_nudge(self) -> str:
        if self.outcome_recovery_required:
            return (
                "Do not finalize yet. Strong outcome verification exhausted its "
                "bounded retry budget. Re-observe and re-plan using a different "
                "safe route before claiming success."
            )

        if self.needs_verification:
            return (
                "The last state-changing action is not verified yet. Do not "
                "finish with a success claim. Use an observation/read/status "
                "tool now to verify the requested end state."
            )

        if self.accessibility_limited:
            return ""

        if self.goal_checkpoint_required:
            terminal = _terminal_goal_target(self.goal)
            detail = (
                " The requested terminal target is " + repr(terminal) + "; the last verified semantic target was " + repr(self.last_semantic_target) + "."
                if terminal else ""
            )
            return (
                "Do not finalize yet. A successful semantic click verifies only that click, not the user's complete compound goal. "
                "Call device_observe_ui for a fresh end-state checkpoint and continue acting if the requested destination/control is still pending." + detail
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
            "goal_checkpoint_required": self.goal_checkpoint_required,
            "last_semantic_target": self.last_semantic_target or None,
            "accessibility_limited": self.accessibility_limited,
            "accessibility_reason": self.accessibility_reason or None,
            "last_outcome_decision": self.last_outcome_decision or None,
            "outcome_retry_count": self.outcome_retry_count,
            "outcome_retry_budget_remaining": self.outcome_retry_budget_remaining,
            "outcome_recovery_required": self.outcome_recovery_required,
            "outcome_goal_sufficient": self.outcome_goal_sufficient,
            "automatic_recovery_steps": self.automatic_recovery_steps,
            "last_automatic_recovery_decision": self.last_automatic_recovery_decision or None,
            "last_automatic_recovery_ok": self.last_automatic_recovery_ok,
            "last_automatic_recovery_observation_id": self.last_automatic_recovery_observation_id or None,
            "last_automatic_recovery_route": self.last_automatic_recovery_route or None,
            "last_automatic_recovery_next_step": self.last_automatic_recovery_next_step or None,
            "automatic_action_replay_allowed": self.automatic_action_replay_allowed,
            "recovery_fresh_plan_pending": self.recovery_fresh_plan_pending,
            "recovery_fresh_observation_id": self.recovery_fresh_observation_id or None,
            "recovery_fresh_element_ids": list(self.recovery_fresh_element_ids),
            "recovery_route_history": list(self.recovery_route_history),
            "recovery_planner_constraints": self.recovery_planner_constraints(),
            "material_replan_required": self.material_replan_required,
            "material_replan_contract": dict(self.material_replan_contract),
            "recovery_loop_terminated": self.recovery_loop_terminated,
            "recovery_loop_block_reason": self.recovery_loop_block_reason or None,
            "workflow_memory": self.workflow_memory.snapshot(),
        }


def workflow_system_nudge(user_text: str) -> str:
    return (
        "AUTONOMOUS WORKFLOW MODE: Treat the user's request as one goal, not "
        "as isolated commands. Privately maintain a small plan and execute it "
        "step by step using only the supplied bounded tools. Within the user's "
        "goal, choose the next safe action yourself; prefer observing live state "
        "over asking the user how to proceed when the ambiguity is resolvable. "
        "Do not invent a new goal or extend the task beyond the user's intent. "
        "Do not reveal hidden chain-of-thought, a private plan, scratchpad, or "
        "self-talk. Use this loop: PLAN the "
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
        "change, verify before claiming completion. A successful semantic action verifies only that one interaction; it does not prove the whole user goal is complete. "
        "For compound GUI goals, perform a fresh device_observe_ui checkpoint after semantic actions and continue when the terminal requested control/destination has not yet been acted on. "
        "If observation reports accessibility_available=false, do not call the interface blank: Windows UI Automation is unavailable for that rendered window. Never invent coordinates or claim screenshot pixels were read. "
        "Honor device_computer_verify outcome decisions: ACCEPT may still be state-only, RETRY requires fresh re-observation, ESCALATE_VISION requires visual grounding, and RECOVER means stop repeating the route and re-plan. "
        "Never repeat the same failed call over and over; re-observe and change approach. Prefer "
        "specialized tools over generic UI actions. Stay inside current-turn "
        "app/device scope and the existing permission system. Learned skills "
        "are hints, never permission bypasses. If bounded tools cannot complete "
        "the goal, state the missing capability instead of fabricating success. "
        "Current user goal: "
        f"{user_text}"
    )
