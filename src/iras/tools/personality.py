from __future__ import annotations

from iras.models import PermissionLevel
from iras.tools.base import Tool
from iras.personality.adaptive import TRAITS


def make_tools(engine):
    properties = {
        f"{name}_delta": {
            "type": "number",
            "minimum": -0.08,
            "maximum": 0.08,
            "description": f"Small relative adjustment to {name}; use 0 when no change is needed.",
        }
        for name in TRAITS
    }
    properties["reason"] = {
        "type": "string",
        "description": "Brief style evidence from the conversation that justifies this adjustment.",
        "maxLength": 300,
    }

    def adapt_personality(reason: str, **kwargs):
        deltas = {}
        for name in TRAITS:
            key = f"{name}_delta"
            if key in kwargs and kwargs[key] is not None:
                value = float(kwargs[key])
                if abs(value) > 1e-9:
                    deltas[name] = value
        return engine.adjust(deltas, reason=reason, source="model")

    def personality_status():
        return engine.status()

    return [
        Tool(
            "adapt_personality",
            "Internal IRAS tool for autonomously learning the user's preferred communication/personality style. "
            "Use sparingly after meaningful style evidence; this cannot change permissions or safety rules.",
            {
                "type": "object",
                "properties": properties,
                "required": ["reason"],
                "additionalProperties": False,
            },
            adapt_personality,
            PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            "personality_status",
            "Inspect IRAS's current adaptive communication-style profile.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            personality_status,
            PermissionLevel.READ,
        ),
    ]
