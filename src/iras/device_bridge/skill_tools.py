from __future__ import annotations

from typing import Any

from iras.device_bridge.skills import (
    PersistentSkillStore,
    render_parameters,
    resolve_semantic_target,
)
from iras.models import PermissionLevel
from iras.tools.base import Tool


def make_tools(device_store, skill_store: PersistentSkillStore | None = None):
    skills = skill_store or PersistentSkillStore()

    def device_skill_find(command, app="", device_id=None):
        match = skills.find(command, app=app)
        return {
            "match": match,
            "found": bool(match),
            "rule": (
                "A learned step is only a hint. Validate every step against a "
                "fresh UI observation before calling device_semantic_action."
            ),
        }

    def device_skill_validate(
        skill_id,
        step_index,
        app="",
        parameters=None,
        device_id=None,
    ):
        skill = skills.get(skill_id)
        if not skill:
            return {
                "valid": False,
                "reason": "skill_not_found",
                "fallback_required": True,
            }
        if skill.status != "active":
            return {
                "valid": False,
                "reason": "skill_demoted",
                "fallback_required": True,
            }
        if not (0 <= int(step_index) < len(skill.steps)):
            return {
                "valid": False,
                "reason": "step_out_of_range",
                "fallback_required": True,
            }

        step = skill.steps[int(step_index)]
        rendered = render_parameters(
            step.to_dict(),
            dict(parameters or {}),
        )
        locator = dict(rendered.get("locator") or {})
        requested_app = str(app or rendered.get("app") or step.app)
        if requested_app.casefold().strip() != skill.app.casefold().strip():
            return {
                "valid": False,
                "reason": "app_scope_mismatch",
                "fallback_required": True,
            }

        # Read-only validation. ensure_open=False prevents the validator from
        # launching a different application behind the user's back.
        observation = device_store.request_and_wait(
            action="observe_ui",
            arguments={
                "app": skill.app,
                "ensure_open": False,
                "max_elements": 220,
                "screenshot": False,
            },
            device_id=device_id,
            timeout=45,
        )
        resolved = resolve_semantic_target(observation, locator)
        if not resolved:
            degraded = skills.record_failure(skill_id)
            return {
                "valid": False,
                "reason": "learned_target_missing",
                "fallback_required": True,
                "confidence": degraded.confidence if degraded else None,
                "status": degraded.status if degraded else "unknown",
                "observation": observation,
                "instruction": (
                    "The learned target is stale. Use this live v3.2 UI "
                    "observation to recover semantically; do not invent "
                    "coordinates. A verified recovered workflow may refresh "
                    "the skill."
                ),
            }

        old_locator = locator
        changed = any(
            str(old_locator.get(key, "")) != str(resolved.get(key, ""))
            for key in ("name", "automation_id", "role")
        )
        if changed:
            skills.adapt_step(skill_id, int(step_index), resolved)

        return {
            "valid": True,
            "skill_id": skill_id,
            "step_index": int(step_index),
            "app": skill.app,
            "action": str(rendered.get("action") or step.action),
            "target": resolved["target"],
            "role": resolved.get("role", ""),
            "occurrence": resolved.get("occurrence", 1),
            "text": str(rendered.get("text") or ""),
            "key": str(rendered.get("key") or ""),
            "replace": bool(rendered.get("replace", False)),
            "expected_state": dict(rendered.get("expected_state") or {}),
            "adapted_locator": changed,
            "instruction": (
                "Execute this step only through device_semantic_action, then "
                "require its verification_observation before continuing."
            ),
        }

    def device_skill_list(app="", include_demoted=False, device_id=None):
        app_key = str(app or "").casefold().strip()
        items = []
        for skill in skills.all(include_demoted=bool(include_demoted)):
            if app_key and skill.app.casefold().strip() != app_key:
                continue
            items.append(
                {
                    "skill_id": skill.skill_id,
                    "app": skill.app,
                    "intent_template": skill.intent_template,
                    "parameters": skill.parameters,
                    "steps": len(skill.steps),
                    "confidence": skill.confidence,
                    "successes": skill.successes,
                    "failures": skill.failures,
                    "status": skill.status,
                    "updated_at": skill.updated_at,
                }
            )
        return {"skills": items, "count": len(items)}

    def device_skill_inspect(skill_id, device_id=None):
        item = skills.inspect(skill_id)
        return {"skill": item, "found": bool(item)}

    def device_skill_delete(skill_id, device_id=None):
        deleted = skills.delete(skill_id)
        return {"deleted": deleted, "skill_id": skill_id}

    optional_device = {
        "device_id": {
            "type": "string",
            "description": "Optional paired device ID.",
        }
    }

    return [
        Tool(
            "device_skill_find",
            (
                "Find a persistent learned semantic workflow for the current "
                "GUI task. This is read-only; every returned step must be "
                "validated live before execution."
            ),
            {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "app": {"type": "string"},
                    **optional_device,
                },
                "required": ["command"],
            },
            device_skill_find,
            PermissionLevel.READ,
        ),
        Tool(
            "device_skill_validate",
            (
                "Validate one learned semantic step against a fresh Windows UI "
                "Automation observation. If stale, returns the live observation "
                "for v3.2 visual-control recovery and demotes repeated failures."
            ),
            {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    "step_index": {"type": "integer", "minimum": 0},
                    "app": {"type": "string"},
                    "parameters": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                    **optional_device,
                },
                "required": ["skill_id", "step_index"],
            },
            device_skill_validate,
            PermissionLevel.READ,
        ),
        Tool(
            "device_skill_list",
            "List learned app skills and their confidence/status.",
            {
                "type": "object",
                "properties": {
                    "app": {"type": "string"},
                    "include_demoted": {"type": "boolean"},
                    **optional_device,
                },
            },
            device_skill_list,
            PermissionLevel.READ,
        ),
        Tool(
            "device_skill_inspect",
            "Inspect one learned semantic app skill without executing it.",
            {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    **optional_device,
                },
                "required": ["skill_id"],
            },
            device_skill_inspect,
            PermissionLevel.READ,
        ),
        Tool(
            "device_skill_delete",
            (
                "Delete one learned app skill. Use only when the user explicitly "
                "asks to forget/delete that skill."
            ),
            {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    **optional_device,
                },
                "required": ["skill_id"],
            },
            device_skill_delete,
            PermissionLevel.SAFE_ACTION,
        ),
    ]
