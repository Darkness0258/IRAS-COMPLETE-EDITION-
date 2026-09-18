from __future__ import annotations
import csv,json
from collections import Counter
from pathlib import Path
from typing import Any

class AuditDashboard:
    def __init__(self,trace_path:str|Path): self.trace_path=Path(trace_path)
    def rows(self,limit:int=500,*,operation:str="",errors_only:bool=False)->list[dict[str,Any]]:
        if not self.trace_path.exists(): return []
        lines=self.trace_path.read_text(encoding="utf-8",errors="replace").splitlines()[-max(limit*4,limit):]; out=[]
        for line in lines:
            try:r=json.loads(line)
            except Exception:continue
            name=str(r.get("name") or r.get("event") or "unknown")
            if operation and operation.lower() not in name.lower():continue
            if errors_only and not (r.get("ok") is False or r.get("error")):continue
            out.append(r)
        return out[-limit:]
    def summary(self,limit:int=500)->dict[str,Any]:
        rows=self.rows(limit); names=Counter(str(r.get("name") or r.get("event") or "unknown") for r in rows); errors=sum(1 for r in rows if r.get("ok") is False or r.get("error")); return {"events":len(rows),"errors":errors,"top_operations":names.most_common(20),"recent":rows[-25:]}
    def export_json(self,path:str|Path,*,limit:int=5000)->str:
        p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(self.rows(limit),ensure_ascii=False,indent=2),encoding="utf-8"); return str(p)
