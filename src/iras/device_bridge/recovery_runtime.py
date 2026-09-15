from __future__ import annotations

import re
from typing import Any

from iras.device_bridge.adaptive_recovery import rank_recovery_routes
from iras.device_bridge.recovery_learning import recovery_learning_context_from_verification


READ_ONLY_RECOVERY_TOOL = "device_computer_observe"
MAX_AUTOMATIC_RECOVERY_STEPS = 4

SEMANTIC_CONDITIONS = {
    "element_exists",
    "element_absent",
    "text_contains",
    "window_title_contains",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _infer_app_from_window_title(title: str) -> str:
    """Return a conservative app token only for titles we can map safely.

    Recovery must never guess an arbitrary executable from a window caption.
    This list intentionally stays small and deterministic.
    """

    text = _norm(title)
    if not text:
        return ""

    mappings = (
        (r"\bwhatsapp\b", "whatsapp"),
        (r"\bspotify\b", "spotify"),
        (r"\bdiscord\b", "discord"),
        (r"\bnotepad\b", "notepad"),
        (r"\bgoogle chrome\b|\bchrome\b", "chrome"),
        (r"\bmicrosoft edge\b|\bedge\b", "edge"),
    )
    for pattern, app in mappings:
        if re.search(pattern, text):
            return app
    return ""


def select_recovery_route(
    verification_output: dict[str, Any] | None,
    verification_arguments: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Select the safest recovery route from verification evidence.

    v3.5.12 separates *route selection* from *route execution*. Read-only
    re-grounding can still run automatically. Focus/reacquisition and full
    re-planning are selected explicitly but are not auto-executed, which keeps
    side-effect policy unchanged from v3.5.11.
    """

    output = _dict(verification_output)
    arguments = _dict(verification_arguments)
    decision = _dict(output.get("decision"))
    action = str(decision.get("action") or "").strip().upper()
    if action not in {"RETRY", "ESCALATE_VISION", "RECOVER"}:
        return None

    assessment = _dict(output.get("assessment"))
    state_delta = _dict(assessment.get("state_delta"))
    observation = _dict(output.get("observation"))
    foreground = _dict(observation.get("foreground"))
    prior_foreground = _dict(output.get("prior_foreground"))

    condition = _norm(output.get("condition") or arguments.get("condition"))
    semantic = condition in SEMANTIC_CONDITIONS
    requested_scope = _norm(arguments.get("scope") or output.get("scope") or "auto")
    if requested_scope not in {"auto", "foreground", "desktop"}:
        requested_scope = "auto"

    reason_codes = {
        str(value) for value in (decision.get("reason_codes") or [])
    }
    evidence_sources = {
        str(value) for value in (assessment.get("evidence_sources") or [])
    }
    vision_escalated = bool(output.get("vision_escalated"))
    uia_actionable = bool(observation.get("uia_actionable"))
    foreground_changed = state_delta.get("foreground_changed") is True

    # If verification drifted to another app/window, the safest next route is
    # to reacquire the prior app only when its identity can be mapped
    # conservatively. Otherwise get a desktop-wide visual read before replanning.
    if foreground_changed:
        app = _infer_app_from_window_title(str(prior_foreground.get("title") or ""))
        if app:
            return {
                "route": "app_refocus_reacquire",
                "tool": "device_app_control",
                "arguments": {"app": app, "action": "focus"},
                "purpose": "restore_expected_foreground_before_reverification",
                "automatic": False,
                "state_changing": True,
                "safe_navigation_only": True,
                "requires_different_route": False,
                "reason_codes": [
                    "foreground_drift_detected",
                    "expected_app_identity_is_conservative",
                ],
            }
        return {
            "route": "desktop_vision",
            "tool": READ_ONLY_RECOVERY_TOOL,
            "arguments": {
                "vision": "always",
                "scope": "desktop",
                "max_elements": 180,
            },
            "purpose": "desktop_reacquisition_after_foreground_drift",
            "automatic": True,
            "state_changing": False,
            "safe_navigation_only": False,
            "requires_different_route": False,
            "reason_codes": ["foreground_drift_detected", "expected_app_unknown"],
        }

    # An explicit policy escalation means UIA/semantic evidence was insufficient.
    if action == "ESCALATE_VISION" or (
        semantic
        and "semantic_target_needs_visual_confirmation" in reason_codes
    ):
        return {
            "route": "foreground_vision",
            "tool": READ_ONLY_RECOVERY_TOOL,
            "arguments": {
                "vision": "always",
                "scope": "foreground" if requested_scope != "desktop" else "desktop",
                "max_elements": 180,
            },
            "purpose": "visual_semantic_regrounding",
            "automatic": True,
            "state_changing": False,
            "safe_navigation_only": False,
            "requires_different_route": False,
            "reason_codes": ["semantic_evidence_requires_visual_grounding"],
        }

    # A bounded RETRY on a stable window should prefer the cheapest semantic
    # re-grounding route. If UIA is actionable, suppress vision for this read.
    if action == "RETRY" and semantic and uia_actionable and not vision_escalated:
        return {
            "route": "uia_reground",
            "tool": READ_ONLY_RECOVERY_TOOL,
            "arguments": {
                "vision": "off",
                "scope": "foreground",
                "max_elements": 180,
            },
            "purpose": "fresh_semantic_uia_regrounding_before_retry",
            "automatic": True,
            "state_changing": False,
            "safe_navigation_only": False,
            "requires_different_route": False,
            "reason_codes": ["stable_foreground", "uia_actionable"],
        }

    # If semantic retry has no dependable UIA route, prefer foreground vision.
    if action == "RETRY" and semantic and (
        not uia_actionable or "vision" not in evidence_sources
    ):
        return {
            "route": "foreground_vision",
            "tool": READ_ONLY_RECOVERY_TOOL,
            "arguments": {
                "vision": "always",
                "scope": "foreground" if requested_scope != "desktop" else "desktop",
                "max_elements": 180,
            },
            "purpose": "visual_semantic_regrounding_before_retry",
            "automatic": True,
            "state_changing": False,
            "safe_navigation_only": False,
            "requires_different_route": False,
            "reason_codes": ["semantic_retry_needs_stronger_grounding"],
        }

    # RECOVER means the bounded retry route has already failed. If foreground
    # vision has already been used and the window is stable, another identical
    # read is unlikely to help; require a different plan instead of looping.
    if action == "RECOVER" and (vision_escalated or "vision" in evidence_sources):
        return {
            "route": "full_replan",
            "tool": None,
            "arguments": {},
            "purpose": "bounded_route_exhausted_choose_different_plan",
            "automatic": False,
            "state_changing": False,
            "safe_navigation_only": False,
            "requires_different_route": True,
            "reason_codes": [
                "retry_budget_exhausted",
                "prior_visual_route_already_attempted",
            ],
        }

    # Generic recovery remains a desktop visual read before replanning. This is
    # the broadest automatic step and is still read-only.
    if action == "RECOVER" or requested_scope == "desktop":
        return {
            "route": "desktop_vision",
            "tool": READ_ONLY_RECOVERY_TOOL,
            "arguments": {
                "vision": "always",
                "scope": "desktop",
                "max_elements": 180,
            },
            "purpose": "desktop_reobserve_before_replan",
            "automatic": True,
            "state_changing": False,
            "safe_navigation_only": False,
            "requires_different_route": True,
            "reason_codes": ["broad_reacquisition_before_replan"],
        }

    # Non-semantic RETRY (for state predicates) only needs a fresh observation.
    return {
        "route": "fresh_observe",
        "tool": READ_ONLY_RECOVERY_TOOL,
        "arguments": {
            "vision": "auto",
            "scope": requested_scope,
            "max_elements": 180,
        },
        "purpose": "fresh_reobservation_before_retry",
        "automatic": True,
        "state_changing": False,
        "safe_navigation_only": False,
        "requires_different_route": False,
        "reason_codes": ["bounded_retry_requires_fresh_state"],
    }


def build_recovery_directive(
    verification_output: dict[str, Any] | None,
    verification_arguments: dict[str, Any] | None = None,
    *,
    planner_constraints: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Map verification evidence to one selected recovery route.

    v3.5.19 keeps the deterministic v3.5.12 route as the live-evidence
    preference, then optionally ranks all *live-supported* safe alternatives
    against bounded recovery history. Hard exclusions remain controller-grade.
    """

    output = _dict(verification_output)
    arguments = _dict(verification_arguments)
    decision = _dict(output.get("decision"))
    action = str(decision.get("action") or "").strip().upper()
    route = select_recovery_route(verification_output, verification_arguments)
    if route is None:
        return None

    adaptive_result = None
    if isinstance(planner_constraints, dict):
        adaptive_result = rank_recovery_routes(
            verification_output,
            verification_arguments,
            planner_constraints,
            preferred_route=route,
        )
        selected = adaptive_result.get("selected_directive")
        if isinstance(selected, dict) and selected.get("route"):
            route = selected

    merged_reasons: list[str] = []
    for value in [
        *(decision.get("reason_codes") or []),
        *(route.get("reason_codes") or []),
    ]:
        text = str(value)
        if text and text not in merged_reasons:
            merged_reasons.append(text)

    verification_context = {
        "condition": str(arguments.get("condition") or output.get("condition") or ""),
        "target": str(arguments.get("target") or output.get("target") or ""),
        "scope": str(arguments.get("scope") or output.get("scope") or "auto"),
        "prior_observation_id": str(arguments.get("prior_observation_id") or ""),
    }
    learning_context = recovery_learning_context_from_verification(output, arguments)

    directive = {
        "decision": action,
        **route,
        "reason_codes": merged_reasons,
        "verification_context": verification_context,
        "learning_context": learning_context,
    }
    if adaptive_result is not None:
        directive["adaptive_recovery"] = {
            key: value
            for key, value in adaptive_result.items()
            if key != "selected_directive"
        }
    return directive


def recovery_route_message(directive: dict[str, Any]) -> str:
    """Model-facing guidance when a route is selected but not auto-executed."""

    route = str(directive.get("route") or "unknown")
    tool = directive.get("tool")
    arguments = _dict(directive.get("arguments"))
    if route == "app_refocus_reacquire" and tool:
        return (
            "AUTOMATIC RECOVERY ROUTE SELECTED: app_refocus_reacquire. "
            f"The expected foreground drifted. Use {tool} with arguments "
            f"{arguments!r} to restore the app, then run a fresh computer "
            "observation and verification. This focus/navigation step was not "
            "auto-executed because v3.5.12 still forbids automatic state-changing "
            "recovery actions."
        )
    return (
        "AUTOMATIC RECOVERY ROUTE SELECTED: full_replan. The bounded retry/visual "
        "route is exhausted. Do not repeat the failed action or the same recovery "
        "path. Re-observe only if needed, choose a materially different safe route, "
        "and verify the semantic end state before finishing."
    )


def recovery_system_message(
    directive: dict[str, Any],
    payload: dict[str, Any],
    *,
    handoff: dict[str, Any] | None = None,
) -> str:
    """Compact model-facing summary for an automatically executed recovery read."""

    ok = bool(payload.get("ok"))
    output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
    observation_id = str(output.get("observation_id") or "")
    foreground = output.get("foreground")
    foreground_title = ""
    if isinstance(foreground, dict):
        foreground_title = str(foreground.get("title") or "")

    elements = output.get("elements")
    element_count = len(elements) if isinstance(elements, list) else int(
        output.get("element_count") or 0
    )
    grounded: list[dict[str, str]] = []
    if isinstance(elements, list):
        for element in elements[:40]:
            if not isinstance(element, dict):
                continue
            grounded.append({
                "element_id": str(element.get("element_id") or ""),
                "label": str(element.get("label") or element.get("name") or ""),
                "role": str(element.get("role") or ""),
            })
    vision_scope = output.get("vision_scope")

    handoff = handoff if isinstance(handoff, dict) else build_recovery_handoff(
        directive, payload
    )
    return (
        "AUTOMATIC OUTCOME RECOVERY ORCHESTRATION: IRAS executed one bounded read-only "
        f"reacquisition step for decision {directive.get('decision')} using "
        f"route {directive.get('route')}. Recovery tool success={ok}; "
        f"purpose={directive.get('purpose')}; observation_id={observation_id or 'none'}; "
        f"foreground={foreground_title or 'unknown'}; element_count={element_count}; "
        f"vision_scope={vision_scope!r}; grounded_elements={grounded!r}; "
        f"next_step={handoff.get('next_step')!r}; "
        f"planner_constraints={handoff.get('planner_constraints')!r}. "
        "Use only this fresh observation_id and grounded element_ids to re-ground the target, "
        "then plan a fresh next action. action_replay_allowed=False: never automatically "
        "repeat the prior click/type/send/submit action. If a different route is required, "
        "re-plan rather than replaying the failed action."
    )


def build_recovery_handoff(
    directive: dict[str, Any],
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the safe planner handoff after a recovery route executes.

    v3.5.13 makes recovery execution explicit: the controller may acquire fresh
    read-only state, but it never grants permission to replay the action that
    failed verification. The planner receives fresh observation identifiers and
    grounded semantic candidates and must choose the next action again.
    """

    data = _dict(payload)
    output = _dict(data.get("output"))
    elements = output.get("elements")
    if not isinstance(elements, list):
        elements = []

    grounded: list[dict[str, Any]] = []
    for element in elements[:60]:
        if not isinstance(element, dict):
            continue
        grounded.append({
            "element_id": str(element.get("element_id") or ""),
            "label": str(element.get("label") or element.get("name") or ""),
            "role": str(element.get("role") or ""),
            "rect": element.get("rect") if isinstance(element.get("rect"), dict) else None,
        })

    foreground = _dict(output.get("foreground"))
    observation_id = str(output.get("observation_id") or "")
    ok = bool(data.get("ok"))
    fresh_state_available = bool(ok and observation_id)
    requires_different_route = bool(directive.get("requires_different_route"))

    if requires_different_route:
        next_step = "replan_different_route"
    elif fresh_state_available:
        next_step = "reground_target_then_plan_fresh_action"
    else:
        next_step = "recovery_failed_replan_or_report_blocker"

    constraints = [
        "use_fresh_observation_only",
        "do_not_replay_state_changing_action",
        "reground_target_before_next_action",
        "verify_semantic_outcome_after_next_action",
    ]
    if requires_different_route:
        constraints.append("choose_materially_different_route")

    return {
        "decision": str(directive.get("decision") or "").upper(),
        "route": str(directive.get("route") or ""),
        "recovery_ok": ok,
        "fresh_state_available": fresh_state_available,
        "fresh_observation_id": observation_id or None,
        "foreground": {
            "title": str(foreground.get("title") or ""),
            "hwnd": foreground.get("hwnd"),
        },
        "vision_scope": output.get("vision_scope"),
        "uia_actionable": output.get("uia_actionable"),
        "element_count": len(elements) if elements else int(output.get("element_count") or 0),
        "grounded_elements": grounded,
        "next_step": next_step,
        "requires_different_route": requires_different_route,
        "action_replay_allowed": False,
        "state_changing_auto_recovery_allowed": False,
        "planner_constraints": constraints,
        "reason_codes": list(directive.get("reason_codes") or []),
        "verification_context": _dict(directive.get("verification_context")),
    }


def execute_recovery_route(
    directive: dict[str, Any],
    execute_tool,
) -> dict[str, Any]:
    """Execute one selected recovery route under the v3.5.13 safety gate.

    Only automatic, read-only ``device_computer_observe`` routes may execute
    here. Safe navigation such as app focus remains planner-controlled, and the
    original state-changing action is never replayed by this orchestrator.
    """

    if not isinstance(directive, dict):
        return {
            "executed": False,
            "blocked_reason": "invalid_recovery_directive",
            "payload": None,
            "handoff": None,
        }

    if directive.get("automatic") is not True:
        return {
            "executed": False,
            "blocked_reason": "route_requires_planner_control",
            "payload": None,
            "handoff": None,
        }

    if directive.get("state_changing") is True:
        return {
            "executed": False,
            "blocked_reason": "state_changing_auto_recovery_forbidden",
            "payload": None,
            "handoff": None,
        }

    tool = str(directive.get("tool") or "")
    if tool != READ_ONLY_RECOVERY_TOOL:
        return {
            "executed": False,
            "blocked_reason": "recovery_tool_not_read_only_allowlisted",
            "payload": None,
            "handoff": None,
        }

    arguments = _dict(directive.get("arguments"))
    try:
        result = execute_tool(tool, arguments)
        payload = {
            "ok": bool(getattr(result, "ok", False)),
            "output": getattr(result, "output", None),
            "error": getattr(result, "error", None),
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "output": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

    handoff = build_recovery_handoff(directive, payload)
    return {
        "executed": True,
        "blocked_reason": None,
        "payload": payload,
        "handoff": handoff,
    }
