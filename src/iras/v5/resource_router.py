from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class ResourceSnapshot:
    cpu_percent: float=0.0
    ram_free_mb: int=0
    gpu_vram_free_mb: int=0
    network_online: bool=True


class ResourceAwareRouter:
    def choose(self, providers:list[dict[str,Any]], *, difficulty:str="normal", resources:ResourceSnapshot|None=None, prefer_local:bool=False)->dict[str,Any]|None:
        resources=resources or ResourceSnapshot()
        candidates=[]
        for p in providers:
            state=str(p.get("state") or p.get("status") or "").upper()
            if state not in {"ONLINE","CONFIGURED","READY"}: continue
            latency=float(p.get("latency_ms") or 9999)
            failures=float(p.get("failure_rate") or 0)
            local=bool(p.get("local")) or str(p.get("name") or "").lower()=="ollama"
            score=100-failures*70-min(latency/50,30)
            if prefer_local and local: score+=25
            if difficulty in {"hard","expert"}: score+=float(p.get("quality_score") or 0)*20
            if local and resources.ram_free_mb and resources.ram_free_mb<2500: score-=40
            candidates.append((score,p))
        return max(candidates,key=lambda x:x[0])[1] if candidates else None
