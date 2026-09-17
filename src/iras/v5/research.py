from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Callable, Any


@dataclass
class ResearchFinding:
    claim: str
    evidence: str
    source: str
    confidence: float = 0.5


@dataclass
class ResearchDossier:
    question: str
    findings: list[ResearchFinding]=field(default_factory=list)
    disagreements: list[str]=field(default_factory=list)
    synthesis: str=""

    def as_dict(self):
        return {"question":self.question,"findings":[asdict(f) for f in self.findings],"disagreements":self.disagreements,"synthesis":self.synthesis}


class AutonomousResearchEngine:
    def run(self, question:str, researchers:list[Callable[[str],dict[str,Any]]], critic:Callable[[str,list[dict[str,Any]]],dict[str,Any]]|None=None,
            synthesizer:Callable[[str,list[dict[str,Any]],dict[str,Any]|None],str]|None=None)->ResearchDossier:
        raw=[]; findings=[]
        for fn in researchers:
            result=fn(question); raw.append(result)
            for item in result.get("findings",[]):
                findings.append(ResearchFinding(str(item.get("claim") or ""),str(item.get("evidence") or ""),str(item.get("source") or ""),float(item.get("confidence") or .5)))
        critique=critic(question,raw) if critic else None
        synthesis=synthesizer(question,raw,critique) if synthesizer else "\n".join(f"- {f.claim}" for f in findings)
        return ResearchDossier(question,findings,list((critique or {}).get("disagreements") or []),synthesis)
