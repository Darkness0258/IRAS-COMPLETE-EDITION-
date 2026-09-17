from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from typing import Any


class AuditDashboard:
    def __init__(self,trace_path:str|Path): self.trace_path=Path(trace_path)
    def rows(self,limit:int=500)->list[dict[str,Any]]:
        if not self.trace_path.exists(): return []
        lines=self.trace_path.read_text(encoding="utf-8",errors="replace").splitlines()[-limit:]
        out=[]
        for line in lines:
            try: out.append(json.loads(line))
            except Exception: continue
        return out
    def summary(self,limit:int=500)->dict[str,Any]:
        rows=self.rows(limit); names=Counter(str(r.get("name") or r.get("event") or "unknown") for r in rows)
        errors=sum(1 for r in rows if r.get("ok") is False or r.get("error"))
        return {"events":len(rows),"errors":errors,"top_operations":names.most_common(20),"recent":rows[-25:]}
