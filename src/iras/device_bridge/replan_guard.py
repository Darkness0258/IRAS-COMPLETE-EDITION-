from __future__ import annotations

import json
from typing import Any


MAX_IDENTICAL_RECOVERY_ROUTE_USES = 2


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def recovery_route_signature(directive: dict[str, Any] | None) -> str:
    """Return a deterministic signature for one selected recovery route.

    Observation ids are intentionally absent because recovery directives are
    route descriptions, not state snapshots. The signature therefore captures
    the actual recovery strategy: route + tool + arguments.
    """

    data = _dict(directive)
    route = str(data.get("route") or "")
    tool = str(data.get("tool") or "")
    arguments = _dict(data.get("arguments"))
    return json.dumps(
        {"route": route, "tool": tool, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def tool_call_signature(tool: str, arguments: dict[str, Any] | None) -> str:
    return (
        str(tool)
        + ":"
        + json.dumps(
            arguments or {},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    )


def recovery_route_use_count(
    history: list[dict[str, Any]] | None,
    directive: dict[str, Any] | None,
) -> int:
    signature = recovery_route_signature(directive)
    if not signature:
        return 0
    count = 0
    for item in history or []:
        if not isinstance(item, dict):
            continue
        item_signature = str(item.get("route_signature") or "")
        if item_signature == signature:
            count += 1
    return count


def recovery_route_cycle_guard(
    history: list[dict[str, Any]] | None,
    directive: dict[str, Any] | None,
    *,
    max_identical_uses: int = MAX_IDENTICAL_RECOVERY_ROUTE_USES,
) -> dict[str, Any]:
    """Decide whether another automatic execution of this route is allowed.

    v3.5.17 deliberately allows a small bounded repeat because a second fresh
    observation can legitimately resolve transient UI state. A third identical
    automatic route is a loop, not recovery, and must return to the planner for
    a materially different strategy.
    """

    data = _dict(directive)
    signature = recovery_route_signature(data)
    uses = recovery_route_use_count(history, data)
    limit = max(1, int(max_identical_uses))
    allowed = bool(signature) and uses < limit
    reason = "" if allowed else "identical_recovery_route_cycle_detected"
    return {
        "allowed": allowed,
        "reason": reason,
        "route": str(data.get("route") or ""),
        "route_signature": signature,
        "previous_uses": uses,
        "max_identical_uses": limit,
        "requires_materially_different_plan": not allowed,
        "action_replay_allowed": False,
    }


def material_replan_contract(
    history: list[dict[str, Any]] | None,
    *,
    blocked_directive: dict[str, Any] | None = None,
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Build the controller-enforced contract for a materially different plan."""

    forbidden_tool_signatures: list[str] = []
    exhausted_routes: list[str] = []

    for item in history or []:
        if not isinstance(item, dict):
            continue
        signature = str(item.get("tool_signature") or "")
        route = str(item.get("route") or "")
        if signature and signature not in forbidden_tool_signatures:
            # A route is considered exhausted only after it has already been
            # used at least twice. The caller may add a newly blocked route below.
            route_signature = str(item.get("route_signature") or "")
            uses = sum(
                1
                for other in (history or [])
                if isinstance(other, dict)
                and str(other.get("route_signature") or "") == route_signature
            )
            if uses >= MAX_IDENTICAL_RECOVERY_ROUTE_USES:
                forbidden_tool_signatures.append(signature)
                if route and route not in exhausted_routes:
                    exhausted_routes.append(route)

    blocked = _dict(blocked_directive)
    if blocked:
        tool = str(blocked.get("tool") or "")
        if tool:
            signature = tool_call_signature(tool, _dict(blocked.get("arguments")))
            if signature not in forbidden_tool_signatures:
                forbidden_tool_signatures.append(signature)
        route = str(blocked.get("route") or "")
        if route and route not in exhausted_routes:
            exhausted_routes.append(route)

    reasons: list[str] = []
    for value in reason_codes or []:
        text = str(value)
        if text and text not in reasons:
            reasons.append(text)
    if not reasons:
        reasons.append("materially_different_plan_required")

    planner_constraints = recovery_history_planner_constraints(
        history,
        exhausted_routes=exhausted_routes,
        forbidden_tool_signatures=forbidden_tool_signatures,
    )

    return {
        "version": "3.5.18",
        "required": True,
        "forbidden_tool_signatures": forbidden_tool_signatures,
        "exhausted_routes": exhausted_routes,
        "reason_codes": reasons,
        "requires_materially_different_plan": True,
        "action_replay_allowed": False,
        "next_step": "choose_strategy_not_in_exhausted_route_set",
        "planner_constraints": planner_constraints,
    }


def materially_different_replan_message(contract: dict[str, Any] | None) -> str:
    data = _dict(contract)
    return (
        "MATERIALLY-DIFFERENT REPLAN GUARD v3.5.17: "
        f"exhausted_routes={list(data.get('exhausted_routes') or [])!r}; "
        f"reason_codes={list(data.get('reason_codes') or [])!r}; "
        "the controller will reject an unchanged exhausted recovery tool call. "
        "Choose a genuinely different safe strategy from current state. "
        + recovery_history_planner_message(data.get("planner_constraints"))
    )


def recovery_history_planner_constraints(
    history: list[dict[str, Any]] | None,
    *,
    exhausted_routes: list[str] | None = None,
    forbidden_tool_signatures: list[str] | None = None,
    max_recent: int = 6,
) -> dict[str, Any]:
    """Build compact recovery-history constraints for the planner.

    v3.5.18 moves loop knowledge *ahead* of the next model decision. The
    controller remains authoritative, but the planner now receives enough
    bounded history to avoid proposing a route that is already exhausted.
    History is evidence about recovery strategies only; it never grants
    permission to replay the state-changing action that originally failed.
    """

    exhausted = []
    for value in exhausted_routes or []:
        route = str(value or "").strip()
        if route and route not in exhausted:
            exhausted.append(route)

    forbidden = []
    for value in forbidden_tool_signatures or []:
        signature = str(value or "").strip()
        if signature and signature not in forbidden:
            forbidden.append(signature)

    rows = [item for item in (history or []) if isinstance(item, dict)]
    stats: dict[str, dict[str, Any]] = {}
    recent: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for index, item in enumerate(rows, start=1):
        route = str(item.get("route") or "").strip()
        if not route:
            continue
        step = int(item.get("automatic_step") or index)
        ok = bool(item.get("ok"))
        entry = stats.setdefault(
            route,
            {
                "route": route,
                "uses": 0,
                "successes": 0,
                "failures": 0,
                "last_step": 0,
                "last_ok": None,
                "tool_signatures": [],
            },
        )
        entry["uses"] += 1
        entry["successes"] += int(ok)
        entry["failures"] += int(not ok)
        entry["last_step"] = max(int(entry["last_step"]), step)
        entry["last_ok"] = ok
        tool_signature = str(item.get("tool_signature") or "").strip()
        if tool_signature and tool_signature not in entry["tool_signatures"]:
            entry["tool_signatures"].append(tool_signature)

        recent_item = {
            "route": route,
            "automatic_step": step,
            "ok": ok,
        }
        recent.append(recent_item)
        if not ok:
            failures.append(recent_item)

    recent = sorted(recent, key=lambda item: int(item["automatic_step"]))[-max(1, int(max_recent)):]
    failures = sorted(failures, key=lambda item: int(item["automatic_step"]))[-max(1, int(max_recent)):]

    successful_alternatives = [
        {
            "route": route,
            "successes": int(data["successes"]),
            "failures": int(data["failures"]),
            "last_step": int(data["last_step"]),
        }
        for route, data in stats.items()
        if int(data["successes"]) > 0 and route not in exhausted
    ]
    successful_alternatives.sort(
        key=lambda item: (int(item["last_step"]), int(item["successes"])),
        reverse=True,
    )

    recent_failed_routes: list[str] = []
    for item in reversed(failures):
        route = str(item.get("route") or "")
        if route and route not in recent_failed_routes and route not in exhausted:
            recent_failed_routes.append(route)

    saturated_routes = sorted(
        route
        for route, data in stats.items()
        if int(data["uses"]) >= MAX_IDENTICAL_RECOVERY_ROUTE_USES
        and route not in exhausted
    )

    return {
        "version": "3.5.18",
        "exhausted_routes": exhausted,
        "forbidden_tool_signatures": forbidden,
        "route_use_counts": {
            route: int(data["uses"])
            for route, data in sorted(stats.items())
        },
        "recent_history": recent,
        "recent_failures": failures,
        "recent_failed_routes": recent_failed_routes,
        "successful_alternatives": successful_alternatives,
        "saturated_routes": saturated_routes,
        "planner_rules": [
            "never_choose_exhausted_route_or_forbidden_signature",
            "deprioritize_recent_failed_routes_when_a_safe_alternative_exists",
            "prefer_recent_successful_alternative_only_when_current_state_supports_it",
            "treat_saturated_route_as_one_step_from_controller_cycle_block",
            "use_current_observation_as_source_of_truth",
            "do_not_replay_prior_state_changing_action",
        ],
        "action_replay_allowed": False,
    }


def recovery_history_planner_message(constraints: dict[str, Any] | None) -> str:
    data = _dict(constraints)
    alternatives = [
        str(item.get("route") or "")
        for item in (data.get("successful_alternatives") or [])
        if isinstance(item, dict) and str(item.get("route") or "")
    ]
    learned = {
        str(route): {
            "success_rate": item.get("success_rate"),
            "effective_samples": item.get("effective_samples"),
        }
        for route, item in _dict(data.get("learned_route_priors")).items()
        if isinstance(item, dict)
    }
    context_prior_count = len(
        _dict(data.get("learned_context_route_priors"))
    )
    return (
        "RECOVERY-HISTORY-AWARE PLANNER CONSTRAINTS v3.5.18 + contextual-learning v3.6.0: "
        f"exhausted_routes={list(data.get('exhausted_routes') or [])!r}; "
        f"recent_failed_routes={list(data.get('recent_failed_routes') or [])!r}; "
        f"successful_alternatives={alternatives!r}; "
        f"saturated_routes={list(data.get('saturated_routes') or [])!r}; "
        f"route_use_counts={dict(data.get('route_use_counts') or {})!r}; "
        f"learned_route_priors={learned!r}; "
        f"contextual_prior_buckets={context_prior_count}. "
        "Do not propose an exhausted route or forbidden tool signature. "
        "Deprioritize a recently failed route when a safe current-state-supported alternative exists. "
        "Persisted global/contextual priors are bounded/decayed guidance only and cannot override live UI evidence. "
        "Use the live observation as source of truth; history is guidance, not proof. "
        "action_replay_allowed=False."
    )
