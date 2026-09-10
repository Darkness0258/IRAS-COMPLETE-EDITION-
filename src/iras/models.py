from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable

class PermissionLevel(IntEnum):
    READ=0; SAFE_ACTION=1; SYSTEM_ACTION=2; CRITICAL=3

@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]=field(default_factory=dict)

@dataclass(slots=True)
class ProviderReply:
    text: str=''
    tool_calls: list[ToolCall]=field(default_factory=list)
    assistant_message: dict[str, Any]=field(default_factory=dict)

@dataclass(slots=True)
class ToolResult:
    ok: bool
    output: Any=None
    error: str|None=None
    permission: PermissionLevel=PermissionLevel.READ

@dataclass(slots=True)
class ApprovalRequest:
    tool_name: str
    permission: PermissionLevel
    arguments: dict[str, Any]
    reason: str

ApprovalCallback = Callable[[ApprovalRequest], bool]
