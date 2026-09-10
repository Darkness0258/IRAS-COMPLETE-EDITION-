from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json, threading
from iras.security.redact import redact

class AuditLogger:
    def __init__(self, path: Path):
        self.path=path; self.path.parent.mkdir(parents=True, exist_ok=True); self._lock=threading.Lock()
    def record(self,event:str,payload:dict):
        row={'timestamp':datetime.now(timezone.utc).isoformat(),'event':event,'payload':redact(payload)}
        with self._lock, self.path.open('a',encoding='utf-8') as f:
            f.write(json.dumps(row,ensure_ascii=False,default=str)+'\n')
