from __future__ import annotations

import time
from typing import Any

APP = "whatsapp"


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _label(element: dict[str, Any]) -> str:
    return str(element.get("label") or element.get("name") or "").strip()


def _element_text(element: dict[str, Any]) -> str:
    return " ".join(
        str(element.get(key) or "")
        for key in ("label", "name", "value", "automation_id", "role")
    ).strip()


def _same_or_overlapping_rect(
    a: dict[str, Any] | None,
    b: dict[str, Any] | None,
) -> bool:
    if not a or not b:
        return False
    try:
        ax1, ay1 = int(a.get("left") or 0), int(a.get("top") or 0)
        ax2 = ax1 + int(a.get("width") or 0)
        ay2 = ay1 + int(a.get("height") or 0)
        bx1, by1 = int(b.get("left") or 0), int(b.get("top") or 0)
        bx2 = bx1 + int(b.get("width") or 0)
        by2 = by1 + int(b.get("height") or 0)
    except (TypeError, ValueError):
        return False

    iw = max(0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0, min(ay2, by2) - max(ay1, by1))
    intersection = iw * ih
    if intersection <= 0:
        return False
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    return intersection / min(area_a, area_b) >= 0.65


def _rect_values(element: dict[str, Any]) -> tuple[int, int, int, int]:
    rect = element.get("rect") or {}
    try:
        return (
            int(rect.get("left") or 0),
            int(rect.get("top") or 0),
            int(rect.get("width") or 0),
            int(rect.get("height") or 0),
        )
    except (TypeError, ValueError):
        return 0, 0, 0, 0


def _in_whatsapp_search_band(element: dict[str, Any]) -> bool:
    left, top, width, height = _rect_values(element)
    return (
        -20 <= left <= 180
        and 55 <= top <= 190
        and 180 <= width <= 520
        and 24 <= height <= 90
        and left + width <= 620
    )


def find_whatsapp_search_target(
    elements: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Ground the semantic WhatsApp search field without geometry-only guesses."""
    scored: list[tuple[int, dict[str, Any]]] = []
    for element in elements:
        label = _label(element).casefold()
        if not label:
            continue
        role = str(element.get("role") or "").casefold()
        element_id = str(element.get("element_id") or "")
        rect = element.get("rect") or {}
        width = int(rect.get("width") or 0)
        height = int(rect.get("height") or 0)

        score = 0
        semantic_match = False
        if "search or start" in label:
            score += 140
            semantic_match = True
        if "search" in label and "chat" in label:
            score += 120
            semantic_match = True
        if "ask meta ai or search" in label:
            score += 120
            semantic_match = True
        if label == "search":
            score += 90
            semantic_match = True
        elif "search" in label:
            score += 70
            semantic_match = True

        if not semantic_match:
            continue
        if role in {"edit", "textbox", "combobox", "input"}:
            score += 45
        if element_id.startswith("vision:"):
            score += 10
        if width >= 140:
            score += 8
        if 20 <= height <= 90:
            score += 5
        if any(term in label for term in ("search messages", "search web")):
            score -= 50
        if score > 0:
            scored.append((score, element))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def find_whatsapp_filled_search_target(
    elements: list[dict[str, Any]],
    *,
    current_query: str = "",
) -> dict[str, Any] | None:
    """Ground placeholder or an already-filled search field using bounded corroboration."""
    scored: list[tuple[int, dict[str, Any]]] = []
    wanted_query = _norm(current_query)
    for element in elements:
        label = _norm(_label(element))
        if not label:
            continue
        role = _norm(element.get("role"))
        element_id = str(element.get("element_id") or "")
        source_is_vision = element_id.startswith("vision:") or _norm(
            element.get("source")
        ) == "vision"
        score = 0
        semantic = False
        if "search or start" in label or "search or stant" in label:
            score += 170
            semantic = True
        elif "search" in label and "chat" in label:
            score += 150
            semantic = True
        elif "ask meta ai or search" in label:
            score += 145
            semantic = True
        elif label == "search":
            score += 120
            semantic = True
        elif "search" in label:
            score += 90
            semantic = True

        if (
            not semantic
            and wanted_query
            and wanted_query in label
            and source_is_vision
            and _in_whatsapp_search_band(element)
        ):
            score += 135
            semantic = True

        if not semantic:
            continue
        if role in {"edit", "textbox", "combobox", "input"}:
            score += 45
        if source_is_vision:
            score += 15
        if _in_whatsapp_search_band(element):
            score += 20
        if "search messages" in label:
            score -= 100
        scored.append((score, element))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def find_contact_target(
    elements: list[dict[str, Any]],
    *,
    contact: str,
    search_rect: dict[str, Any] | None,
) -> dict[str, Any] | None:
    wanted = _norm(contact)
    scored: list[tuple[int, dict[str, Any]]] = []
    for element in elements:
        label = _norm(_label(element))
        haystack = _norm(_element_text(element))
        if not label or wanted not in haystack:
            continue
        if _same_or_overlapping_rect(element.get("rect") or {}, search_rect):
            continue
        role = _norm(element.get("role"))
        if role in {"edit", "textbox", "combobox", "input"}:
            continue
        if "search" in label and "darkness" in label:
            continue

        score = 0
        if label == wanted:
            score += 170
        elif label.startswith(wanted):
            score += 130
        else:
            score += 90
        if role in {"listitem", "dataitem", "button", "text", "hyperlink", "icon"}:
            score += 25
        if str(element.get("element_id") or "").startswith("vision:"):
            score += 15
        rect = element.get("rect") or {}
        if search_rect:
            search_bottom = int(search_rect.get("top") or 0) + int(
                search_rect.get("height") or 0
            )
            element_top = int(rect.get("top") or 0)
            if element_top >= search_bottom:
                score += 20
        scored.append((score, element))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def find_composer_target(elements: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored: list[tuple[int, dict[str, Any]]] = []
    for element in elements:
        label = _norm(_label(element))
        haystack = _norm(_element_text(element))
        role = _norm(element.get("role"))
        if not haystack:
            continue

        score = 0
        semantic = False
        if "type a message" in haystack:
            score += 180
            semantic = True
        elif "type message" in haystack:
            score += 170
            semantic = True
        elif "message" == label:
            score += 130
            semantic = True
        elif role in {"edit", "textbox", "input"} and "message" in haystack:
            score += 125
            semantic = True
        if not semantic:
            continue
        if role in {"edit", "textbox", "input", "combobox"}:
            score += 45
        if str(element.get("element_id") or "").startswith("vision:"):
            score += 10
        if "search" in haystack:
            score -= 120
        scored.append((score, element))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _foreground_probe(executor: Any) -> dict[str, Any]:
    return executor.computer_observe(
        vision="off",
        scope="foreground",
        max_elements=8,
    )


def wait_for_app_ready(
    executor: Any,
    *,
    timeout: float = 10.0,
    poll_seconds: float = 0.35,
    stable_probes: int = 2,
) -> dict[str, Any]:
    """Reacquire Store/UWP apps across transient launch-window handoffs."""
    deadline = time.monotonic() + max(1.0, float(timeout))
    required_stable = max(1, int(stable_probes))
    stable_hits = 0
    attempts: list[dict[str, Any]] = []
    last_title = ""

    while time.monotonic() < deadline:
        focus = None
        focus_error = None
        try:
            focus = executor.app_control(APP, "focus")
        except RuntimeError as exc:
            focus_error = f"{type(exc).__name__}: {exc}"

        try:
            observation = _foreground_probe(executor)
            foreground = observation.get("foreground") or {}
            title = str(foreground.get("title") or "")
            last_title = title
            is_whatsapp = "whatsapp" in _norm(title)
        except Exception as exc:
            title = ""
            is_whatsapp = False
            attempts.append(
                {
                    "focus": focus,
                    "focus_error": focus_error,
                    "probe_error": f"{type(exc).__name__}: {exc}",
                }
            )
        else:
            attempts.append(
                {
                    "focus": focus,
                    "focus_error": focus_error,
                    "foreground": title,
                    "foreground_hwnd": foreground.get("hwnd"),
                }
            )

        if is_whatsapp:
            stable_hits += 1
            if stable_hits >= required_stable:
                return {
                    "ready": True,
                    "focus": focus,
                    "foreground": title,
                    "stable_probes": stable_hits,
                    "reacquire_attempts": attempts,
                }
        else:
            stable_hits = 0
        time.sleep(max(0.05, float(poll_seconds)))

    raise RuntimeError(
        "IRAS launched WhatsApp but could not prove a stable foreground "
        f"window within {timeout:.1f}s (last foreground={last_title!r}). "
        "No message was typed or sent."
    )


def ensure_app(executor: Any) -> dict[str, Any]:
    try:
        focus = executor.app_control(APP, "focus")
        ready = wait_for_app_ready(
            executor,
            timeout=4.0,
            poll_seconds=0.25,
            stable_probes=1,
        )
        return {"mode": "focused_existing", "focus": focus, "ready": ready}
    except RuntimeError:
        launch = executor.open_app(APP)
        ready = wait_for_app_ready(
            executor,
            timeout=12.0,
            poll_seconds=0.35,
            stable_probes=2,
        )
        return {
            "mode": "launched",
            "launch": launch,
            "focus": ready.get("focus"),
            "ready": ready,
        }
