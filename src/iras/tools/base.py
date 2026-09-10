from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from iras.models import PermissionLevel

PermissionResolver=Callable[[dict[str,Any]], PermissionLevel]

@dataclass(slots=True)
class Tool:
    name:str
    description:str
    schema:dict[str,Any]
    handler:Callable[...,Any]
    permission:PermissionLevel=PermissionLevel.READ
    permission_resolver:PermissionResolver|None=None
    def required_permission(self,args): return self.permission_resolver(args) if self.permission_resolver else self.permission
    def openai_schema(self):
        return {'type':'function','function':{'name':self.name,'description':self.description,'parameters':self.schema}}
