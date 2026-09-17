from __future__ import annotations
from typing import Callable, Any


class AgentDebate:
    def run(self, objective:str, *, proposer:Callable[[str],Any], challenger:Callable[[str,Any],Any], tester:Callable[[str,Any,Any],Any], coordinator:Callable[[str,Any,Any,Any],Any])->dict[str,Any]:
        proposal=proposer(objective)
        challenge=challenger(objective,proposal)
        test=tester(objective,proposal,challenge)
        decision=coordinator(objective,proposal,challenge,test)
        return {"objective":objective,"proposal":proposal,"challenge":challenge,"test":test,"decision":decision}
