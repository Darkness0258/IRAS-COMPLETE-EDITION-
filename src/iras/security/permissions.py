from __future__ import annotations
from dataclasses import dataclass
from iras.models import PermissionLevel, ApprovalCallback, ApprovalRequest

class PermissionDenied(RuntimeError): pass

@dataclass(slots=True)
class PermissionEngine:
    auto_level: PermissionLevel=PermissionLevel.SAFE_ACTION
    approval_callback: ApprovalCallback|None=None
    always_confirm_critical: bool=True
    hard_cap: PermissionLevel=PermissionLevel.CRITICAL

    def authorize(self, request: ApprovalRequest) -> None:
        level=request.permission
        if level > self.hard_cap:
            raise PermissionDenied(f'{request.tool_name} exceeds this runtime permission cap.')
        requires_prompt = level > self.auto_level or (self.always_confirm_critical and level==PermissionLevel.CRITICAL)
        if not requires_prompt: return
        if self.approval_callback and self.approval_callback(request): return
        raise PermissionDenied(f'{request.tool_name} requires {level.name} approval and was not approved.')
