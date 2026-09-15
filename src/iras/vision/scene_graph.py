from __future__ import annotations

import hashlib
import json
import re
from typing import Any


SCENE_GRAPH_VERSION = "3.7.0"


def _norm(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9.+ ]+", " ", text)
    return " ".join(text.split())


def _rect(element: dict) -> dict:
    raw = element.get("rect") if isinstance(element, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    return {
        "left": int(raw.get("left", 0) or 0),
        "top": int(raw.get("top", 0) or 0),
        "width": max(0, int(raw.get("width", 0) or 0)),
        "height": max(0, int(raw.get("height", 0) or 0)),
    }


def _normalized_geometry(element: dict, region: dict) -> tuple[int, int, int, int]:
    rect = _rect(element)
    region = region if isinstance(region, dict) else {}
    left = int(region.get("left", 0) or 0)
    top = int(region.get("top", 0) or 0)
    width = max(1, int(region.get("width", 1) or 1))
    height = max(1, int(region.get("height", 1) or 1))

    # 2% buckets make IDs stable across tiny OCR/layout jitter while still
    # separating repeated controls located in materially different positions.
    def bucket(value: float) -> int:
        return int(round(value * 50.0))

    return (
        bucket((rect["left"] - left) / width),
        bucket((rect["top"] - top) / height),
        bucket(rect["width"] / width),
        bucket(rect["height"] / height),
    )


def stable_element_id(element: dict, *, region: dict) -> str:
    source = str(element.get("source") or "unknown").strip().lower()
    prefix = "vision" if source in {"vision", "omniparser"} else "uia" if source == "uia" else source
    identity = {
        "source": prefix,
        "role": _norm(element.get("role")),
        "name": _norm(element.get("name")),
        "automation_id": _norm(element.get("automation_id")),
        "label": _norm(element.get("label")),
        "geometry": _normalized_geometry(element, region),
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:14]
    return f"{prefix}:{digest}"


def visual_element_confidence(raw: dict) -> float:
    for key in ("confidence", "score", "conf", "probability"):
        value = raw.get(key)
        try:
            if value is not None:
                parsed = float(value)
                if parsed > 1.0 and parsed <= 100.0:
                    parsed /= 100.0
                return max(0.0, min(parsed, 1.0))
        except (TypeError, ValueError):
            pass

    content = _norm(raw.get("content") or raw.get("text"))
    interactive = bool(raw.get("interactivity", True))
    if content and interactive:
        return 0.82
    if content:
        return 0.77
    if interactive:
        return 0.74
    return 0.68


def _semantic_key(element: dict) -> str:
    return "|".join(
        (
            _norm(element.get("label")),
            _norm(element.get("name")),
            _norm(element.get("automation_id")),
            _norm(element.get("role")),
        )
    )


def _iou(a: dict, b: dict) -> float:
    ra = _rect(a)
    rb = _rect(b)
    ax2 = ra["left"] + ra["width"]
    ay2 = ra["top"] + ra["height"]
    bx2 = rb["left"] + rb["width"]
    by2 = rb["top"] + rb["height"]
    left = max(ra["left"], rb["left"])
    top = max(ra["top"], rb["top"])
    right = min(ax2, bx2)
    bottom = min(ay2, by2)
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    union = ra["width"] * ra["height"] + rb["width"] * rb["height"] - intersection
    return float(intersection / union) if union > 0 else 0.0


def _with_metadata(element: dict, *, region: dict, capture_sha256: str) -> dict:
    item = dict(element)
    source = str(item.get("source") or "unknown").lower()
    item["element_id"] = stable_element_id(item, region=region)
    confidence = item.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        if source == "uia":
            confidence = 0.99 if bool(item.get("interactive")) else 0.94
        else:
            confidence = 0.78
    item["confidence"] = round(max(0.0, min(float(confidence), 1.0)), 3)
    item["provenance"] = {
        "source": source,
        "backend": "windows_uia" if source == "uia" else "omniparser" if source in {"vision", "omniparser"} else source,
        "capture_sha256": capture_sha256 or None,
    }
    item.setdefault("sources", [source])
    return item


def build_scene_graph(
    uia_elements: list[dict],
    vision_elements: list[dict],
    *,
    region: dict,
    capture_sha256: str = "",
) -> dict:
    """Fuse UIA and visual grounding into one stable scene graph.

    UIA remains authoritative where both backends identify the same control.
    Vision-only elements remain available for WebViews/canvas/Electron surfaces.
    Each element receives a deterministic ID, confidence, and provenance.
    """
    uia = [
        _with_metadata(item, region=region, capture_sha256=capture_sha256)
        for item in (uia_elements or [])
        if isinstance(item, dict)
    ]
    vision = [
        _with_metadata(item, region=region, capture_sha256=capture_sha256)
        for item in (vision_elements or [])
        if isinstance(item, dict)
    ]

    fused = list(uia)
    suppressed_visual = 0
    for visual in vision:
        visual_key = _semantic_key(visual)
        duplicate = None
        for accessible in uia:
            same_semantics = bool(visual_key.strip("|") and visual_key == _semantic_key(accessible))
            overlapping = _iou(visual, accessible) >= 0.72
            if overlapping and (same_semantics or _norm(visual.get("label")) == _norm(accessible.get("label"))):
                duplicate = accessible
                break
        if duplicate is not None:
            sources = set(duplicate.get("sources") or [])
            sources.add("omniparser")
            duplicate["sources"] = sorted(sources)
            duplicate["visual_corrobation"] = True
            duplicate["confidence"] = round(max(float(duplicate.get("confidence", 0.0)), float(visual.get("confidence", 0.0))), 3)
            suppressed_visual += 1
            continue
        fused.append(visual)

    labels: dict[str, list[dict]] = {}
    for item in fused:
        if not bool(item.get("interactive")):
            continue
        label = _norm(item.get("label") or item.get("name") or item.get("automation_id"))
        if label:
            labels.setdefault(label, []).append(item)
    ambiguous = 0
    for items in labels.values():
        if len(items) > 1:
            ambiguous += len(items)
            for item in items:
                item["ambiguous_label"] = True

    source_counts = {
        "uia": sum(1 for item in fused if str(item.get("source")) == "uia"),
        "vision": sum(1 for item in fused if str(item.get("source")) in {"vision", "omniparser"}),
    }
    actionable = [item for item in fused if bool(item.get("interactive")) and bool(item.get("enabled", True))]
    visual_only = [item for item in fused if str(item.get("source")) in {"vision", "omniparser"}]

    return {
        "version": SCENE_GRAPH_VERSION,
        "elements": fused,
        "element_count": len(fused),
        "actionable_count": len(actionable),
        "visual_only_count": len(visual_only),
        "ambiguous_actionable_count": ambiguous,
        "source_counts": source_counts,
        "suppressed_visual_duplicates": suppressed_visual,
        "max_confidence": max((float(item.get("confidence", 0.0)) for item in fused), default=0.0),
    }
