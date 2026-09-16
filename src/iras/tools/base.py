from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from iras.models import PermissionLevel

PermissionResolver = Callable[[dict[str, Any]], PermissionLevel]


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "string": return isinstance(value, str)
    if expected == "integer": return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number": return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean": return isinstance(value, bool)
    if expected == "object": return isinstance(value, dict)
    if expected == "array": return isinstance(value, list)
    if expected == "null": return value is None
    return True


def _validate_schema(value: Any, schema: dict[str, Any], path: str = "arguments") -> None:
    if not isinstance(schema, dict):
        return
    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(_type_ok(value, item) for item in expected):
            raise ValueError(f"{path} has the wrong type.")
    elif isinstance(expected, str) and not _type_ok(value, expected):
        raise ValueError(f"{path} must be {expected}.")

    if "enum" in schema and value not in schema.get("enum", []):
        raise ValueError(f"{path} must be one of: {', '.join(map(str, schema['enum']))}.")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path} is below the minimum {schema['minimum']}.")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path} exceeds the maximum {schema['maximum']}.")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise ValueError(f"{path} is too short.")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ValueError(f"{path} is too long.")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise ValueError(f"{path} has too few items.")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ValueError(f"{path} has too many items.")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_schema(item, item_schema, f"{path}[{index}]")

    if isinstance(value, dict):
        required = schema.get("required") or []
        for name in required:
            if name not in value:
                raise ValueError(f"{path}.{name} is required.")
        properties = schema.get("properties") or {}
        for name, item in value.items():
            child = properties.get(name)
            if isinstance(child, dict):
                _validate_schema(item, child, f"{path}.{name}")
            elif schema.get("additionalProperties") is False:
                raise ValueError(f"{path}.{name} is not an allowed argument.")
            elif isinstance(schema.get("additionalProperties"), dict):
                _validate_schema(item, schema["additionalProperties"], f"{path}.{name}")


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    handler: Callable[..., Any]
    permission: PermissionLevel = PermissionLevel.READ
    permission_resolver: PermissionResolver | None = None

    def required_permission(self, args):
        return self.permission_resolver(args) if self.permission_resolver else self.permission

    def validate_arguments(self, args: Any) -> dict[str, Any]:
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise ValueError(f"Arguments for {self.name} must be an object.")
        _validate_schema(args, self.schema, "arguments")
        return args

    def openai_schema(self):
        return {'type': 'function', 'function': {'name': self.name, 'description': self.description, 'parameters': self.schema}}
