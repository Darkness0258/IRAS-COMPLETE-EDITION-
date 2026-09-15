from __future__ import annotations

import os
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


def _rect_overlap_ratio(
    a: dict[str, Any] | None,
    b: dict[str, Any] | None,
) -> float:
    if not a or not b:
        return 0.0
    try:
        ax1, ay1 = int(a.get("left") or 0), int(a.get("top") or 0)
        ax2 = ax1 + int(a.get("width") or 0)
        ay2 = ay1 + int(a.get("height") or 0)
        bx1, by1 = int(b.get("left") or 0), int(b.get("top") or 0)
        bx2 = bx1 + int(b.get("width") or 0)
        by2 = by1 + int(b.get("height") or 0)
    except (TypeError, ValueError):
        return 0.0
    iw = max(0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0, min(ay2, by2) - max(ay1, by1))
    intersection = iw * ih
    if intersection <= 0:
        return 0.0
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    return float(intersection / min(area_a, area_b))


def find_whatsapp_search_target(
    elements: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return a semantically grounded global WhatsApp chat-search field."""
    scored: list[tuple[int, dict[str, Any]]] = []
    for element in elements:
        label = _norm(_label(element))
        if not label:
            continue
        role = _norm(element.get("role"))
        score = 0
        semantic = False
        if "search or start" in label or "search or stant" in label:
            score += 180
            semantic = True
        elif "search" in label and "chat" in label:
            score += 160
            semantic = True
        elif "ask meta ai or search" in label:
            score += 150
            semantic = True
        elif label == "search":
            score += 120
            semantic = True
        elif "search" in label:
            score += 80
            semantic = True
        if not semantic:
            continue
        if "search messages" in label or "search web" in label:
            score -= 120
        if role in {"edit", "textbox", "combobox", "input"}:
            score += 45
        if str(element.get("element_id") or "").startswith("vision:"):
            score += 10
        left, top, width, height = _rect_values(element)
        if width >= 140:
            score += 8
        if 20 <= height <= 100:
            score += 5
        # Global chat search is normally in the left pane near the top. This is
        # only a corroborating signal; semantic text is required above.
        if left <= 520 and top <= 240:
            score += 10
        scored.append((score, element))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def find_chat_header_target(
    elements: list[dict[str, Any]],
    *,
    contact: str,
    foreground_rect: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Find an exact contact label in the right-pane chat-header band.

    This intentionally does not treat a matching name in the chat list as proof
    that the requested conversation is open.
    """
    wanted = _norm(contact)
    if not wanted:
        return None
    rect = foreground_rect or {}
    try:
        window_left = int(rect.get("left") or 0)
        window_top = int(rect.get("top") or 0)
        window_width = max(1, int(rect.get("width") or 1))
        window_height = max(1, int(rect.get("height") or 1))
    except (TypeError, ValueError):
        return None

    header_bottom = window_top + max(100, min(190, int(window_height * 0.20)))
    content_left = window_left + max(250, int(window_width * 0.22))
    scored: list[tuple[int, dict[str, Any]]] = []
    for element in elements:
        label = _norm(_label(element))
        if not label or wanted not in _norm(_element_text(element)):
            continue
        role = _norm(element.get("role"))
        if role in {"edit", "textbox", "combobox", "input"}:
            continue
        left, top, width, height = _rect_values(element)
        center_y = top + height // 2
        if center_y > header_bottom or left < content_left:
            continue
        score = 0
        if label == wanted:
            score += 200
        elif label.startswith(wanted):
            score += 150
        else:
            score += 100
        if role in {"text", "button", "listitem", "dataitem", "icon"}:
            score += 20
        if width <= 500 and height <= 120:
            score += 10
        if str(element.get("element_id") or "").startswith("vision:"):
            score += 15
        scored.append((score, element))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def find_contact_target(
    elements: list[dict[str, Any]],
    *,
    contact: str,
    search_rect: dict[str, Any] | None,
    foreground_rect: dict[str, Any] | None,
) -> dict[str, Any] | None:
    wanted = _norm(contact)
    if not wanted:
        return None
    window = foreground_rect or {}
    try:
        window_left = int(window.get("left") or 0)
        window_width = max(1, int(window.get("width") or 1))
        pane_right = window_left + int(window_width * 0.58)
    except (TypeError, ValueError):
        pane_right = 10_000

    scored: list[tuple[int, dict[str, Any]]] = []
    for element in elements:
        label = _norm(_label(element))
        haystack = _norm(_element_text(element))
        if not label or wanted not in haystack:
            continue
        if _rect_overlap_ratio(element.get("rect") or {}, search_rect) >= 0.65:
            continue
        role = _norm(element.get("role"))
        if role in {"edit", "textbox", "combobox", "input"}:
            continue
        if "search" in label:
            continue
        left, top, width, height = _rect_values(element)
        if left > pane_right:
            # Matching text in the right conversation pane is not a search-list
            # result. Header verification is handled separately.
            continue

        score = 0
        if label == wanted:
            score += 190
        elif label.startswith(wanted):
            score += 145
        else:
            score += 95
        if role in {"listitem", "dataitem", "button", "text", "hyperlink", "icon"}:
            score += 25
        if str(element.get("element_id") or "").startswith("vision:"):
            score += 15
        if search_rect:
            search_bottom = int(search_rect.get("top") or 0) + int(
                search_rect.get("height") or 0
            )
            if top >= search_bottom:
                score += 20
        if 18 <= height <= 140 and width <= 900:
            score += 5
        scored.append((score, element))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    # Fail closed when two visually distinct candidates are essentially tied.
    if len(scored) > 1 and (scored[0][0] - scored[1][0]) < 15:
        return None
    return scored[0][1]


def _foreground_is_whatsapp(computer: Any) -> bool:
    try:
        foreground = computer._foreground()  # controller-local, read-only state
    except Exception:
        return False
    return "whatsapp" in _norm(foreground.get("title"))


def ensure_whatsapp_foreground(ui: Any, computer: Any) -> dict[str, Any]:
    """Focus an existing WhatsApp window or launch it, then prove foreground."""
    mode = "focused_existing"
    try:
        focus = ui.app_control(APP, "focus")
    except RuntimeError:
        launch = ui.catalog.launch(APP)
        focus = None
        mode = "launched"
    else:
        launch = None

    deadline = time.monotonic() + (12.0 if mode == "launched" else 4.0)
    last_error = ""
    while time.monotonic() < deadline:
        if _foreground_is_whatsapp(computer):
            return {
                "ready": True,
                "mode": mode,
                "launch": launch,
                "focus": focus,
            }
        try:
            focus = ui.app_control(APP, "focus")
        except RuntimeError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.25)

    raise RuntimeError(
        "IRAS could not prove WhatsApp was the foreground window. "
        "No message was typed or sent."
        + (f" Last focus error: {last_error}" if last_error else "")
    )


def _roi_fastpath_enabled(computer: Any) -> bool:
    raw = os.getenv("IRAS_WHATSAPP_ROI_FASTPATH", "true").strip().lower()
    enabled = raw in {"1", "true", "yes", "on", "enabled"}
    return bool(enabled and callable(getattr(computer, "observe_region", None)))


def _fractional_region(
    rect: dict[str, Any],
    *,
    left: float,
    top: float,
    width: float,
    height: float,
) -> dict[str, int]:
    x = int(rect.get("left", 0) or 0)
    y = int(rect.get("top", 0) or 0)
    w = max(1, int(rect.get("width", 1) or 1))
    h = max(1, int(rect.get("height", 1) or 1))
    return {
        "left": x + int(w * left),
        "top": y + int(h * top),
        "width": max(1, int(w * width)),
        "height": max(1, int(h * height)),
    }


def _roi_observation(
    computer: Any,
    foreground_rect: dict[str, Any],
    *,
    purpose: str,
) -> dict[str, Any]:
    if purpose == "top":
        region = _fractional_region(
            foreground_rect, left=0.0, top=0.0, width=1.0, height=0.25
        )
    elif purpose == "results":
        region = _fractional_region(
            foreground_rect, left=0.0, top=0.07, width=0.48, height=0.70
        )
    elif purpose == "header":
        region = _fractional_region(
            foreground_rect, left=0.26, top=0.0, width=0.74, height=0.22
        )
    else:
        raise ValueError(f"Unsupported WhatsApp ROI purpose: {purpose}")
    return computer.observe_region(
        region=region,
        label=f"whatsapp_{purpose}",
        mode="text",
        max_elements=120,
    )


def _performance_entry(observation: dict[str, Any]) -> dict[str, Any]:
    perf = dict(observation.get("performance") or {})
    perf["roi_label"] = observation.get("roi_label")
    perf["vision_cache_hit"] = bool(observation.get("vision_cache_hit"))
    perf["vision_parse_mode"] = observation.get("vision_parse_mode")
    return perf


def _fresh_visual_observation(computer: Any) -> dict[str, Any]:
    return computer.observe(vision="always", scope="foreground", max_elements=180)


def _fresh_navigation_observation(computer: Any) -> dict[str, Any]:
    # Auto uses UIA when it is genuinely actionable and falls back to visual
    # grounding for WebView/custom-rendered surfaces.
    return computer.observe(vision="auto", scope="foreground", max_elements=180)


def _observation_header(
    observation: dict[str, Any],
    *,
    contact: str,
) -> dict[str, Any] | None:
    return find_chat_header_target(
        list(observation.get("elements") or []),
        contact=contact,
        foreground_rect=(observation.get("foreground") or {}).get("rect") or {},
    )


def open_chat_and_verify(
    ui: Any,
    computer: Any,
    *,
    contact: str,
) -> dict[str, Any]:
    """Open one WhatsApp chat and visually verify its header without sending.

    R4 keeps the R3 no-model/no-send safety boundary but narrows expensive visual
    grounding to controller-owned regions of interest. Text-heavy search/header
    steps request the bridge's EasyOCR-only mode; if that capability is absent,
    the computer controller falls back to full OmniParser on the same small ROI.
    Every state-changing input still consumes one fresh observation.
    """
    contact = " ".join(str(contact or "").strip().split())
    if not contact or len(contact) > 160 or any(ch in contact for ch in "\r\n\x00"):
        raise ValueError("contact must be a short single-line WhatsApp display name.")

    app_state = ensure_whatsapp_foreground(ui, computer)
    observations = 0
    actions: list[dict[str, Any]] = []
    perception: list[dict[str, Any]] = []

    # R4 fast path: first inspect only the top band. It contains both the global
    # search field and the active chat header, so an already-open target can end
    # after one small text-only parse.
    if _roi_fastpath_enabled(computer):
        try:
            foreground = computer._foreground()
            foreground_rect = foreground.get("rect") or {}
            observation = _roi_observation(
                computer, foreground_rect, purpose="top"
            )
            observations += 1
            perception.append(_performance_entry(observation))

            header = _observation_header(observation, contact=contact)
            if header is not None:
                return {
                    "app": APP,
                    "contact": contact,
                    "verified": True,
                    "verified_header": _label(header),
                    "header_element_id": header.get("element_id"),
                    "verification_source": "vision_roi_text",
                    "observation_id": observation.get("observation_id"),
                    "observations": observations,
                    "actions": actions,
                    "messages_sent": 0,
                    "typed_into_composer": False,
                    "action_replay_allowed": False,
                    "vision_cache_hit": bool(observation.get("vision_cache_hit")),
                    "roi_fastpath": True,
                    "perception": perception,
                    "app_state": app_state,
                }

            elements = list(observation.get("elements") or [])
            search = find_whatsapp_search_target(elements)
            contact_target = find_contact_target(
                elements,
                contact=contact,
                search_rect=(search or {}).get("rect") if search else None,
                foreground_rect=foreground_rect,
            )

            if contact_target is None and search is not None:
                typed = computer.action(
                    observation_id=str(observation.get("observation_id") or ""),
                    action="type_into",
                    element_id=str(search.get("element_id") or ""),
                    text=contact,
                    replace=True,
                    verify=False,
                )
                actions.append(
                    {
                        "action": "type_into_search",
                        "element_id": search.get("element_id"),
                        "observation_consumed": typed.get("observation_consumed"),
                        "roi": "top",
                    }
                )
                time.sleep(0.18)
                observation = _roi_observation(
                    computer, foreground_rect, purpose="results"
                )
                observations += 1
                perception.append(_performance_entry(observation))
                elements = list(observation.get("elements") or [])
                refreshed_search = find_whatsapp_search_target(elements)
                search_rect = (
                    (refreshed_search or {}).get("rect")
                    or search.get("rect")
                    or {}
                )
                contact_target = find_contact_target(
                    elements,
                    contact=contact,
                    search_rect=search_rect,
                    foreground_rect=foreground_rect,
                )

            if contact_target is not None:
                clicked = computer.action(
                    observation_id=str(observation.get("observation_id") or ""),
                    action="click",
                    element_id=str(contact_target.get("element_id") or ""),
                    verify=False,
                    allow_controller_disambiguation=True,
                )
                actions.append(
                    {
                        "action": "open_chat",
                        "element_id": contact_target.get("element_id"),
                        "observation_consumed": clicked.get("observation_consumed"),
                        "controller_disambiguation": True,
                        "roi": observation.get("roi_label"),
                    }
                )
                time.sleep(0.18)

                verification = _roi_observation(
                    computer, foreground_rect, purpose="header"
                )
                observations += 1
                perception.append(_performance_entry(verification))
                header = _observation_header(verification, contact=contact)
                if header is None:
                    # One bounded read-only ROI retry covers delayed WebView paint.
                    time.sleep(0.22)
                    verification = _roi_observation(
                        computer, foreground_rect, purpose="header"
                    )
                    observations += 1
                    perception.append(_performance_entry(verification))
                    header = _observation_header(verification, contact=contact)

                if header is not None:
                    return {
                        "app": APP,
                        "contact": contact,
                        "verified": True,
                        "verified_header": _label(header),
                        "header_element_id": header.get("element_id"),
                        "verification_source": "vision_roi_text",
                        "observation_id": verification.get("observation_id"),
                        "observations": observations,
                        "actions": actions,
                        "messages_sent": 0,
                        "typed_into_composer": False,
                        "action_replay_allowed": False,
                        "vision_cache_hit": bool(verification.get("vision_cache_hit")),
                        "roi_fastpath": True,
                        "perception": perception,
                        "app_state": app_state,
                    }
                # The click is never replayed. We only broaden read-only evidence
                # once below to avoid a false failure from OCR missing the header.
        except (RuntimeError, ValueError, OSError):
            # ROI acceleration must never weaken compatibility. Fall through to
            # the R3 full-scene path; it retains all safety invariants.
            pass

    observation = _fresh_navigation_observation(computer)
    observations += 1

    # The user asked for visual verification, so a UIA-only observation can
    # guide navigation but cannot be the terminal proof.
    if bool(observation.get("vision_available")):
        header = _observation_header(observation, contact=contact)
        if header is not None:
            return {
                "app": APP,
                "contact": contact,
                "verified": True,
                "verified_header": _label(header),
                "header_element_id": header.get("element_id"),
                "verification_source": "vision",
                "observation_id": observation.get("observation_id"),
                "observations": observations,
                "actions": actions,
                "messages_sent": 0,
                "typed_into_composer": False,
                "action_replay_allowed": False,
                "roi_fastpath": False,
                "perception": perception,
                "app_state": app_state,
            }

    elements = list(observation.get("elements") or [])
    foreground_rect = (observation.get("foreground") or {}).get("rect") or {}
    search = find_whatsapp_search_target(elements)
    contact_target = find_contact_target(
        elements,
        contact=contact,
        search_rect=(search or {}).get("rect") if search else None,
        foreground_rect=foreground_rect,
    )

    if contact_target is None and search is None and not bool(observation.get("vision_available")):
        observation = _fresh_visual_observation(computer)
        observations += 1
        elements = list(observation.get("elements") or [])
        foreground_rect = (observation.get("foreground") or {}).get("rect") or {}
        header = _observation_header(observation, contact=contact)
        if header is not None:
            return {
                "app": APP,
                "contact": contact,
                "verified": True,
                "verified_header": _label(header),
                "header_element_id": header.get("element_id"),
                "verification_source": "vision",
                "observation_id": observation.get("observation_id"),
                "observations": observations,
                "actions": actions,
                "messages_sent": 0,
                "typed_into_composer": False,
                "action_replay_allowed": False,
                "roi_fastpath": False,
                "perception": perception,
                "app_state": app_state,
            }
        search = find_whatsapp_search_target(elements)
        contact_target = find_contact_target(
            elements,
            contact=contact,
            search_rect=(search or {}).get("rect") if search else None,
            foreground_rect=foreground_rect,
        )

    if contact_target is None:
        if search is None:
            raise RuntimeError(
                "IRAS could not uniquely ground WhatsApp's global chat search field "
                "or the requested contact. No message was typed or sent."
            )
        typed = computer.action(
            observation_id=str(observation.get("observation_id") or ""),
            action="type_into",
            element_id=str(search.get("element_id") or ""),
            text=contact,
            replace=True,
            verify=False,
        )
        actions.append(
            {
                "action": "type_into_search",
                "element_id": search.get("element_id"),
                "observation_consumed": typed.get("observation_consumed"),
            }
        )
        time.sleep(0.35)
        observation = _fresh_visual_observation(computer)
        observations += 1
        elements = list(observation.get("elements") or [])
        foreground_rect = (observation.get("foreground") or {}).get("rect") or {}
        refreshed_search = find_whatsapp_search_target(elements)
        search_rect = (refreshed_search or {}).get("rect") or search.get("rect") or {}
        contact_target = find_contact_target(
            elements,
            contact=contact,
            search_rect=search_rect,
            foreground_rect=foreground_rect,
        )

    if contact_target is None:
        raise RuntimeError(
            f"IRAS searched WhatsApp for {contact!r} but could not uniquely ground "
            "the contact result. No message was typed or sent."
        )

    clicked = computer.action(
        observation_id=str(observation.get("observation_id") or ""),
        action="click",
        element_id=str(contact_target.get("element_id") or ""),
        verify=False,
        allow_controller_disambiguation=True,
    )
    actions.append(
        {
            "action": "open_chat",
            "element_id": contact_target.get("element_id"),
            "observation_consumed": clicked.get("observation_consumed"),
            "controller_disambiguation": True,
        }
    )
    time.sleep(0.35)

    verification = _fresh_visual_observation(computer)
    observations += 1
    header = _observation_header(verification, contact=contact)
    if header is None:
        time.sleep(0.35)
        verification = _fresh_visual_observation(computer)
        observations += 1
        header = _observation_header(verification, contact=contact)

    if header is None:
        raise RuntimeError(
            f"WhatsApp navigation completed, but fresh visual evidence did not "
            f"prove the chat header is {contact!r}. No message was sent."
        )

    return {
        "app": APP,
        "contact": contact,
        "verified": True,
        "verified_header": _label(header),
        "header_element_id": header.get("element_id"),
        "verification_source": "vision",
        "observation_id": verification.get("observation_id"),
        "observations": observations,
        "actions": actions,
        "messages_sent": 0,
        "typed_into_composer": False,
        "action_replay_allowed": False,
        "vision_cache_hit": bool(verification.get("vision_cache_hit")),
        "roi_fastpath": False,
        "perception": perception,
        "app_state": app_state,
    }

