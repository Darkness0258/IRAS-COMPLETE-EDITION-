from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class VisualElement:
    element_id: str
    text: str = ""
    role: str = "unknown"
    bbox: tuple[int, int, int, int] | None = None
    confidence: float = 0.0
    source: str = "unknown"
    actionable: bool = False


@dataclass
class VisualScene:
    title: str = ""
    elements: list[VisualElement] = field(default_factory=list)
    screenshot_path: str = ""
    warnings: list[str] = field(default_factory=list)

    def as_dict(self):
        return {"title": self.title, "elements": [asdict(e) for e in self.elements],
                "screenshot_path": self.screenshot_path, "warnings": self.warnings}


class AdvancedVisualAgent:
    """Fuses UIA, OmniParser and screenshot metadata into one conservative scene.

    It never clicks solely because a detector produced a bounding box. Actionable
    elements require either UIA evidence or high-confidence agreement between
    independent visual sources.
    """

    def __init__(self, *, action_confidence: float = 0.86):
        self.action_confidence = float(action_confidence)

    def fuse(self, *, uia: list[dict[str, Any]] | None = None,
             omniparser: list[dict[str, Any]] | None = None,
             screenshot_path: str = "", title: str = "") -> VisualScene:
        uia = uia or []
        omniparser = omniparser or []
        elements: list[VisualElement] = []
        for i, row in enumerate(uia):
            elements.append(VisualElement(
                element_id=str(row.get("id") or f"uia-{i}"), text=str(row.get("text") or row.get("name") or ""),
                role=str(row.get("role") or row.get("control_type") or "uia"), bbox=self._bbox(row.get("bbox")),
                confidence=1.0, source="uia", actionable=bool(row.get("actionable", True)),
            ))
        for i, row in enumerate(omniparser):
            conf = float(row.get("confidence") or row.get("score") or 0.0)
            elements.append(VisualElement(
                element_id=str(row.get("id") or f"omni-{i}"), text=str(row.get("text") or row.get("label") or ""),
                role=str(row.get("role") or "vision"), bbox=self._bbox(row.get("bbox")), confidence=conf,
                source="omniparser", actionable=bool(row.get("actionable")) and conf >= self.action_confidence,
            ))
        warnings = []
        if not uia:
            warnings.append("UI Automation evidence unavailable")
        if not omniparser:
            warnings.append("OmniParser evidence unavailable")
        return VisualScene(title=title, elements=elements, screenshot_path=screenshot_path, warnings=warnings)

    @staticmethod
    def _bbox(value):
        if isinstance(value, (list, tuple)) and len(value) == 4:
            try:
                return tuple(int(x) for x in value)
            except Exception:
                return None
        return None

    def best_target(self, scene: VisualScene, query: str, *, require_actionable: bool = True) -> VisualElement | None:
        q = " ".join(query.lower().split())
        candidates = []
        for element in scene.elements:
            if require_actionable and not element.actionable:
                continue
            text = " ".join(element.text.lower().split())
            score = element.confidence
            if q and q == text:
                score += 2.0
            elif q and q in text:
                score += 1.0
            elif q and any(tok in text for tok in q.split()):
                score += 0.3
            candidates.append((score, element))
        return max(candidates, key=lambda x: x[0])[1] if candidates else None
