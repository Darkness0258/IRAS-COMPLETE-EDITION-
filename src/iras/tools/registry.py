from __future__ import annotations

import time

from iras.models import (
    ApprovalRequest,
    ToolResult,
)
from iras.security.permissions import (
    PermissionDenied,
)


class ToolRegistry:
    def __init__(
        self,
        permissions,
        audit,
    ):
        self._tools = {}
        self.permissions = permissions
        self.audit = audit

    def register(self, tool):
        if tool.name in self._tools:
            raise ValueError(
                f"Duplicate tool: "
                f"{tool.name}"
            )

        self._tools[
            tool.name
        ] = tool

    def names(self):
        return sorted(
            self._tools
        )

    def schemas(
        self,
        names=None,
    ):
        if names is None:
            selected = self.names()
        else:
            selected = [
                name
                for name in names
                if name in self._tools
            ]

        return [
            self._tools[name]
            .openai_schema()
            for name in selected
        ]

    def describe(self):
        return [
            {
                "name": t.name,
                "description": t.description,
                "permission": int(
                    t.permission
                ),
            }
            for t in (
                self._tools.values()
            )
        ]

    def execute(
        self,
        name,
        args,
    ):
        tool = self._tools.get(
            name
        )

        if not tool:
            return ToolResult(
                False,
                error=(
                    "Unknown tool: "
                    f"{name}"
                ),
            )

        try:
            args = tool.validate_arguments(args)
        except Exception as exc:
            self.audit.record(
                "tool_invalid_arguments",
                {"tool": name, "error": f"{type(exc).__name__}: {exc}"},
            )
            return ToolResult(False, error=f"Invalid arguments: {exc}")

        level = (
            tool
            .required_permission(args)
        )

        req = ApprovalRequest(
            name,
            level,
            args,
            f"{name} requested "
            f"{level.name}",
        )

        try:
            self.permissions.authorize(
                req
            )

            self.audit.record(
                "tool_call",
                {
                    "tool": name,
                    "permission": (
                        level.name
                    ),
                    "arguments": args,
                },
            )

            started = time.perf_counter()
            out = tool.handler(
                **args
            )
            duration_ms = int((time.perf_counter() - started) * 1000)

            self.audit.record(
                "tool_result",
                {
                    "tool": name,
                    "ok": True,
                    "duration_ms": duration_ms,
                },
            )

            return ToolResult(
                True,
                output=out,
                permission=level,
            )

        except PermissionDenied as exc:
            self.audit.record(
                "tool_denied",
                {
                    "tool": name,
                    "permission": (
                        level.name
                    ),
                    "reason": str(exc),
                },
            )

            return ToolResult(
                False,
                error=str(exc),
                permission=level,
            )

        except Exception as exc:
            self.audit.record(
                "tool_error",
                {
                    "tool": name,
                    "permission": (
                        level.name
                    ),
                    "error": repr(exc),
                },
            )

            return ToolResult(
                False,
                error=(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
                permission=level,
            )
