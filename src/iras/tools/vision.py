from __future__ import annotations

from iras.models import PermissionLevel
from iras.tools.base import Tool
from iras.vision.omniparser_runtime import OmniParserRuntimeManager


def make_tools(manager: OmniParserRuntimeManager | None = None) -> list[Tool]:
    runtime = manager or OmniParserRuntimeManager()

    def status():
        return runtime.status()

    def start():
        result = runtime.ensure_ready(start=True)
        if result.ready:
            runtime.start_supervisor(eager=False)
        return result.as_dict()

    def restart():
        result = runtime.restart()
        if result.ready:
            runtime.start_supervisor(eager=False)
        return result.as_dict()

    def stop():
        runtime.stop_supervisor()
        return runtime.stop().as_dict()

    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    return [
        Tool(
            name="vision_runtime_status",
            description=(
                "Inspect IRAS-managed OmniParser readiness, ownership, bridge, "
                "watchdog, and model warmup state."
            ),
            schema=empty,
            handler=status,
            permission=PermissionLevel.READ,
        ),
        Tool(
            name="vision_runtime_start",
            description=(
                "Start or attach to IRAS's local OmniParser vision service and "
                "enable its health watchdog."
            ),
            schema=empty,
            handler=start,
            permission=PermissionLevel.SAFE_ACTION,
        ),
        Tool(
            name="vision_runtime_restart",
            description=(
                "Restart only an IRAS-managed local OmniParser bridge. External "
                "vision endpoints are never killed or restarted."
            ),
            schema=empty,
            handler=restart,
            permission=PermissionLevel.SYSTEM_ACTION,
        ),
        Tool(
            name="vision_runtime_stop",
            description=(
                "Stop only the authenticated IRAS-managed OmniParser bridge and "
                "disable this process's watchdog."
            ),
            schema=empty,
            handler=stop,
            permission=PermissionLevel.SYSTEM_ACTION,
        ),
    ]
