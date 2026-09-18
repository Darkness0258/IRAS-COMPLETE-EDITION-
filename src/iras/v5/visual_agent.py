from __future__ import annotations
from dataclasses import dataclass,field,asdict
from typing import Any

@dataclass
class VisualElement:
    element_id:str; text:str=""; role:str="unknown"; bbox:tuple[int,int,int,int]|None=None; confidence:float=0.0; source:str="unknown"; actionable:bool=False; evidence:list[str]=field(default_factory=list)
@dataclass
class VisualScene:
    title:str=""; elements:list[VisualElement]=field(default_factory=list); screenshot_path:str=""; warnings:list[str]=field(default_factory=list)
    def as_dict(self):return {"title":self.title,"elements":[asdict(e) for e in self.elements],"screenshot_path":self.screenshot_path,"warnings":self.warnings}

class AdvancedVisualAgent:
    """Fuses UIA, accessibility and OmniParser evidence conservatively."""
    def __init__(self,*,action_confidence:float=.86):self.action_confidence=float(action_confidence)
    @staticmethod
    def _bbox(value):
        if isinstance(value,(list,tuple)) and len(value)==4:
            try:return tuple(int(x) for x in value)
            except Exception:return None
        return None
    @staticmethod
    def _iou(a,b)->float:
        if not a or not b:return 0.0
        ax1,ay1,ax2,ay2=a; bx1,by1,bx2,by2=b; ix1,iy1=max(ax1,bx1),max(ay1,by1); ix2,iy2=min(ax2,bx2),min(ay2,by2)
        inter=max(0,ix2-ix1)*max(0,iy2-iy1); ua=max(0,ax2-ax1)*max(0,ay2-ay1)+max(0,bx2-bx1)*max(0,by2-by1)-inter
        return inter/ua if ua else 0.0
    def fuse(self,*,uia:list[dict[str,Any]]|None=None,accessibility:list[dict[str,Any]]|None=None,omniparser:list[dict[str,Any]]|None=None,screenshot_path:str="",title:str="")->VisualScene:
        uia=uia or []; accessibility=accessibility or []; omni=omniparser or []; elements=[]
        for src,rows,base_conf in (("uia",uia,1.0),("accessibility",accessibility,.96)):
            for i,row in enumerate(rows):
                elements.append(VisualElement(str(row.get("id") or f"{src}-{i}"),str(row.get("text") or row.get("name") or ""),str(row.get("role") or row.get("control_type") or src),self._bbox(row.get("bbox")),base_conf,src,bool(row.get("actionable",True)),[src]))
        for i,row in enumerate(omni):
            conf=float(row.get("confidence") or row.get("score") or 0); box=self._bbox(row.get("bbox")); text=str(row.get("text") or row.get("label") or "")
            agreements=[]
            for existing in elements:
                text_match=bool(text and existing.text and text.lower().strip() in existing.text.lower().strip() or existing.text.lower().strip() in text.lower().strip()) if text and existing.text else False
                if text_match or self._iou(box,existing.bbox)>=.45:agreements.append(existing.source)
            actionable=bool(row.get("actionable")) and (conf>=self.action_confidence or bool(agreements))
            effective=min(1.0,conf+(.08 if agreements else 0))
            elements.append(VisualElement(str(row.get("id") or f"omni-{i}"),text,str(row.get("role") or "vision"),box,effective,"omniparser",actionable,["omniparser",*agreements]))
        warnings=[]
        if not uia:warnings.append("UI Automation evidence unavailable")
        if not accessibility:warnings.append("Accessibility-tree evidence unavailable")
        if not omni:warnings.append("OmniParser evidence unavailable")
        return VisualScene(title,elements,screenshot_path,warnings)
    def best_target(self,scene:VisualScene,query:str,*,require_actionable:bool=True)->VisualElement|None:
        q=" ".join(query.lower().split()); candidates=[]
        for e in scene.elements:
            if require_actionable and not e.actionable:continue
            text=" ".join(e.text.lower().split()); score=e.confidence+.08*max(0,len(set(e.evidence))-1)
            if q and q==text:score+=2
            elif q and q in text:score+=1
            elif q and any(tok in text for tok in q.split()):score+=.3
            candidates.append((score,e))
        return max(candidates,key=lambda x:x[0])[1] if candidates else None
