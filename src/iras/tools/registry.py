from __future__ import annotations
from iras.models import ApprovalRequest, ToolResult
from iras.security.permissions import PermissionEngine, PermissionDenied

class ToolRegistry:
    def __init__(self, permissions, audit): self._tools={}; self.permissions=permissions; self.audit=audit
    def register(self,tool):
        if tool.name in self._tools: raise ValueError(f'Duplicate tool: {tool.name}')
        self._tools[tool.name]=tool
    def names(self): return sorted(self._tools)
    def schemas(self): return [self._tools[n].openai_schema() for n in self.names()]
    def describe(self): return [{'name':t.name,'description':t.description,'permission':int(t.permission)} for t in self._tools.values()]
    def execute(self,name,args):
        tool=self._tools.get(name)
        if not tool: return ToolResult(False,error=f'Unknown tool: {name}')
        level=tool.required_permission(args)
        req=ApprovalRequest(name,level,args,f'{name} requested {level.name}')
        try:
            self.permissions.authorize(req)
            self.audit.record('tool_call',{'tool':name,'permission':level.name,'arguments':args})
            out=tool.handler(**args)
            self.audit.record('tool_result',{'tool':name,'ok':True})
            return ToolResult(True,output=out,permission=level)
        except PermissionDenied as e:
            self.audit.record('tool_denied',{'tool':name,'permission':level.name,'reason':str(e)})
            return ToolResult(False,error=str(e),permission=level)
        except Exception as e:
            self.audit.record('tool_error',{'tool':name,'permission':level.name,'error':repr(e)})
            return ToolResult(False,error=f'{type(e).__name__}: {e}',permission=level)
