from __future__ import annotations

from iras.master_control import MasterControl
from iras.models import PermissionLevel
from iras.tools.base import Tool


def make_tools(master: MasterControl):
    return [
        Tool(
            "master_control_status",
            "Read the locally owner-armed IRAS Master Control state, remaining time, Remote capability flags, and configured filesystem roots.",
            {"type": "object", "properties": {}},
            master.status,
            PermissionLevel.READ,
        ),
        Tool(
            "master_control_disable",
            "Disable the locally armed IRAS Master Control session and restore the previous Remote policy. This can never enable Master Control.",
            {"type": "object", "properties": {}},
            lambda: master.disable(source="agent_requested_disable"),
            PermissionLevel.SAFE_ACTION,
        ),
    ]
