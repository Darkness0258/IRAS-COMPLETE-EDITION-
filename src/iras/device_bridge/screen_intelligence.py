from __future__ import annotations

from pathlib import Path
from typing import Any


def screen_change_score(previous_path: str | Path, current_path: str | Path) -> float | None:
    """Return a bounded 0..1 visual-change score using tiny grayscale previews."""
    try:
        from PIL import Image, ImageChops, ImageStat

        prev = Path(previous_path)
        cur = Path(current_path)
        if not prev.is_file() or not cur.is_file():
            return None
        with Image.open(prev) as a, Image.open(cur) as b:
            a = a.convert("L").resize((160, 90))
            b = b.convert("L").resize((160, 90))
            diff = ImageChops.difference(a, b)
            mean = float(ImageStat.Stat(diff).mean[0])
            return round(max(0.0, min(mean / 255.0, 1.0)), 4)
    except Exception:
        return None


def _compact_element(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "element_id": str(item.get("element_id") or ""),
        "label": str(item.get("label") or item.get("name") or "")[:300],
        "role": str(item.get("role") or "")[:120],
        "source": str(item.get("source") or "")[:80],
    }


def temporal_delta(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    if not previous:
        return {
            "has_previous": False,
            "changed": True,
            "change_level": "initial",
            "screen_change_score": None,
            "foreground_changed": False,
            "appeared": [],
            "disappeared": [],
            "stable_element_count": 0,
        }

    prev_elements = {
        str(item.get("element_id") or ""): item
        for item in (previous.get("elements") or [])
        if isinstance(item, dict) and str(item.get("element_id") or "")
    }
    cur_elements = {
        str(item.get("element_id") or ""): item
        for item in (current.get("elements") or [])
        if isinstance(item, dict) and str(item.get("element_id") or "")
    }
    appeared_ids = sorted(cur_elements.keys() - prev_elements.keys())
    disappeared_ids = sorted(prev_elements.keys() - cur_elements.keys())
    stable = cur_elements.keys() & prev_elements.keys()

    prev_fg = previous.get("foreground") or {}
    cur_fg = current.get("foreground") or {}
    foreground_changed = (
        int(prev_fg.get("hwnd") or 0) != int(cur_fg.get("hwnd") or 0)
        or str(prev_fg.get("title") or "") != str(cur_fg.get("title") or "")
        or int(prev_fg.get("pid") or 0) != int(cur_fg.get("pid") or 0)
    )

    prev_path = ((previous.get("screenshot") or {}).get("path") or "")
    cur_path = ((current.get("screenshot") or {}).get("path") or "")
    visual_score = screen_change_score(prev_path, cur_path) if prev_path and cur_path else None
    denom = max(1, len(prev_elements), len(cur_elements))
    semantic_score = min(1.0, (len(appeared_ids) + len(disappeared_ids)) / float(denom))
    effective = max(float(visual_score or 0.0), semantic_score, 0.3 if foreground_changed else 0.0)
    if effective >= 0.35:
        level = "major"
    elif effective >= 0.08:
        level = "minor"
    else:
        level = "stable"

    return {
        "has_previous": True,
        "previous_observation_id": previous.get("observation_id"),
        "changed": level != "stable",
        "change_level": level,
        "screen_change_score": visual_score,
        "semantic_change_score": round(semantic_score, 4),
        "foreground_changed": foreground_changed,
        "appeared": [_compact_element(cur_elements[key]) for key in appeared_ids[:30]],
        "disappeared": [_compact_element(prev_elements[key]) for key in disappeared_ids[:30]],
        "stable_element_count": len(stable),
    }


def summarize_observation(observation: dict[str, Any]) -> dict[str, Any]:
    elements = [item for item in (observation.get("elements") or []) if isinstance(item, dict)]
    actionable = [item for item in elements if bool(item.get("interactive")) and bool(item.get("enabled", True))]
    labels: list[str] = []
    seen: set[str] = set()
    for item in actionable:
        label = " ".join(str(item.get("label") or item.get("name") or "").split())
        key = label.casefold()
        if label and key not in seen:
            seen.add(key)
            labels.append(label[:200])
            if len(labels) >= 30:
                break
    windows = observation.get("visible_windows") or []
    return {
        "foreground": observation.get("foreground") or {},
        "visible_window_count": len(windows),
        "visible_windows": [
            {
                "title": str(item.get("title") or "")[:300],
                "process": str(item.get("process") or "")[:120],
                "pid": int(item.get("pid") or 0),
                "foreground": bool(item.get("foreground")),
            }
            for item in windows[:20]
            if isinstance(item, dict)
        ],
        "element_count": len(elements),
        "actionable_count": len(actionable),
        "top_actionable_labels": labels,
        "temporal": observation.get("temporal") or {},
        "vision_status": observation.get("vision_status"),
        "vision_scope": observation.get("vision_scope"),
        "uia_available": bool(observation.get("uia_available")),
    }
