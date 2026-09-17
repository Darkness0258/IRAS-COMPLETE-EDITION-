from __future__ import annotations
import ipaddress
from typing import Any,Callable


class HomeNetworkHub:
    """Restricted adapter hub; no discovery/scanning is performed automatically."""
    def __init__(self,allowed_networks:list[str]|None=None):
        self.allowed=[ipaddress.ip_network(x,strict=False) for x in (allowed_networks or ["127.0.0.0/8"])]
        self.adapters:dict[str,Any]={}
    def host_allowed(self,host:str)->bool:
        try: ip=ipaddress.ip_address(host); return any(ip in net for net in self.allowed)
        except ValueError: return host in {"localhost"}
    def register(self,name:str,adapter:Any)->None: self.adapters[name]=adapter
    def invoke(self,name:str,action:str,*,host:str,approval:Callable[[str,str],bool]|None=None,**kwargs):
        if not self.host_allowed(host): raise PermissionError("Host is outside configured home/network allowlist.")
        adapter=self.adapters.get(name)
        if adapter is None: raise KeyError(name)
        if action not in set(getattr(adapter,"allowed_actions",())): raise PermissionError("Adapter action is not declared.")
        if action not in set(getattr(adapter,"read_only_actions",())):
            if not approval or not approval(name,action): raise PermissionError("State-changing home/network action requires approval.")
        return getattr(adapter,action)(host=host,**kwargs)
