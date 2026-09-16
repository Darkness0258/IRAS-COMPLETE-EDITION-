from __future__ import annotations

import os
import threading
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


def _cold_roi_retries() -> int:
    try:
        raw = int(os.getenv("IRAS_WHATSAPP_COLD_ROI_RETRIES", "2"))
    except (TypeError, ValueError):
        raw = 2
    return max(1, min(raw, 3))


def _cold_settle_seconds() -> float:
    try:
        ms = int(os.getenv("IRAS_WHATSAPP_COLD_SETTLE_MS", "220"))
    except (TypeError, ValueError):
        ms = 220
    return max(0.08, min(ms / 1000.0, 0.75))


def _start_visual_prewarm(computer: Any) -> tuple[dict[str, Any], threading.Thread | None]:
    """Start local vision readiness in parallel with WhatsApp focus/paint.

    The worker performs only runtime startup/model warmup. It does not observe,
    click, type, or grant authorization. The first real ROI observation still
    captures fresh pixels and receives its own single-use action binding.
    """
    state: dict[str, Any] = {
        "started": False,
        "complete": False,
        "ready": False,
        "status": None,
        "elapsed_ms": None,
    }
    runtime = getattr(computer, "omniparser", None)
    ensure = getattr(runtime, "ensure_ready", None)
    if not callable(ensure):
        return state, None

    def worker() -> None:
        started = time.perf_counter()
        try:
            result = ensure(start=True)
            state["ready"] = bool(getattr(result, "ready", False))
            state["status"] = getattr(result, "status", None)
        except Exception as exc:  # startup is advisory; observation handles failure
            state["status"] = f"{type(exc).__name__}: {exc}"
        finally:
            state["complete"] = True
            state["elapsed_ms"] = int((time.perf_counter() - started) * 1000)

    state["started"] = True
    thread = threading.Thread(
        target=worker,
        name="iras-whatsapp-vision-prewarm",
        daemon=True,
    )
    thread.start()
    return state, thread


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
    elif purpose == "search":
        # Dedicated left/top search band is intentionally smaller than R4's
        # full top strip. On cold starts this reduces OCR work and avoids letting
        # an early paint miss force the expensive full Florence/YOLO fallback.
        region = _fractional_region(
            foreground_rect, left=0.0, top=0.02, width=0.52, height=0.24
        )
    elif purpose == "results":
        region = _fractional_region(
            foreground_rect, left=0.0, top=0.07, width=0.48, height=0.70
        )
    elif purpose == "header":
        region = _fractional_region(
            foreground_rect, left=0.26, top=0.0, width=0.74, height=0.22
        )
    elif purpose == "workspace":
        # R6 text-only whole-foreground rescue. This is intentionally still OCR
        # only: WhatsApp navigation targets are text semantics, so a cold ROI
        # miss must not eagerly load the Florence/YOLO caption stack.
        region = _fractional_region(
            foreground_rect, left=0.0, top=0.0, width=1.0, height=1.0
        )
    else:
        raise ValueError(f"Unsupported WhatsApp ROI purpose: {purpose}")
    observe_region = getattr(computer, "observe_region", None)
    if callable(observe_region):
        return observe_region(
            region=region,
            label=f"whatsapp_{purpose}",
            mode="text",
            max_elements=120,
        )

    # Compatibility path for older controller adapters and deterministic test
    # doubles. Production UniversalComputerController exposes observe_region, so
    # the v4 text-only ROI path remains authoritative on Windows. This fallback
    # does not replay any action; it only obtains a fresh observation.
    return computer.observe(vision="auto", scope="foreground", max_elements=120)


def _performance_entry(observation: dict[str, Any]) -> dict[str, Any]:
    perf = dict(observation.get("performance") or {})
    perf["roi_label"] = observation.get("roi_label")
    perf["vision_cache_hit"] = bool(observation.get("vision_cache_hit"))
    perf["vision_parse_mode"] = observation.get("vision_parse_mode")
    return perf


def _fresh_visual_observation(computer: Any) -> dict[str, Any]:
    return computer.observe(vision="always", scope="foreground", max_elements=180)


def _full_vision_fallback_enabled() -> bool:
    raw = os.getenv("IRAS_WHATSAPP_FULL_VISION_FALLBACK", "false").strip().lower()
    return raw in {"1", "true", "yes", "on", "enabled"}


def _fresh_navigation_observation(computer: Any) -> dict[str, Any]:
    # Auto uses UIA when it is genuinely actionable and falls back to visual
    # grounding for WebView/custom-rendered surfaces.
    return computer.observe(vision="auto", scope="foreground", max_elements=180)


def _fresh_uia_observation(computer: Any) -> dict[str, Any]:
    # R5 uses a cheap accessibility-only read before conceding to full visual
    # fallback. This never satisfies the user's requested visual terminal proof.
    return computer.observe(vision="off", scope="foreground", max_elements=180)


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

    v4/R6 preserves the no-model/no-send fast path while hardening cold startup.
    Local vision startup/EasyOCR warmup overlaps WhatsApp focus, and all normal
    recovery remains OCR/UIA text-first. Heavy Florence/YOLO semantics are an
    explicit opt-in last resort only. Every state-changing input still consumes
    one fresh observation and is never automatically replayed.
    """
    contact = " ".join(str(contact or "").strip().split())
    if not contact or len(contact) > 160 or any(ch in contact for ch in "\r\n\x00"):
        raise ValueError("contact must be a short single-line WhatsApp display name.")

    roi_enabled = _roi_fastpath_enabled(computer)
    prewarm_state: dict[str, Any] = {
        "started": False,
        "complete": False,
        "ready": False,
        "status": None,
        "elapsed_ms": None,
    }
    prewarm_thread = None
    if roi_enabled:
        prewarm_state, prewarm_thread = _start_visual_prewarm(computer)

    # Focus/launch happens concurrently with bridge startup and EasyOCR prewarm.
    app_state = ensure_whatsapp_foreground(ui, computer)
    observations = 0
    actions: list[dict[str, Any]] = []
    perception: list[dict[str, Any]] = []
    roi_failure_reason = ""
    settle = _cold_settle_seconds()
    retry_budget = _cold_roi_retries()

    def verified_result(
        observation: dict[str, Any],
        header: dict[str, Any],
        *,
        source: str,
        roi_fastpath: bool,
        route: str,
    ) -> dict[str, Any]:
        if prewarm_thread is not None and prewarm_thread.is_alive():
            prewarm_thread.join(timeout=0.01)
        return {
            "app": APP,
            "contact": contact,
            "verified": True,
            "verified_header": _label(header),
            "header_element_id": header.get("element_id"),
            "verification_source": source,
            "observation_id": observation.get("observation_id"),
            "observations": observations,
            "actions": actions,
            "messages_sent": 0,
            "typed_into_composer": False,
            "action_replay_allowed": False,
            "vision_cache_hit": bool(observation.get("vision_cache_hit")),
            "roi_fastpath": roi_fastpath,
            "perception": perception,
            "app_state": app_state,
            "route": route,
            "prewarm": dict(prewarm_state),
        }

    if roi_enabled:
        try:
            foreground = computer._foreground()
            foreground_rect = foreground.get("rect") or {}

            # 1) Small right-header ROI first. If the requested chat is already
            # open, cold and warm paths both finish with one visual observation.
            header_observation = _roi_observation(
                computer, foreground_rect, purpose="header"
            )
            observations += 1
            perception.append(_performance_entry(header_observation))
            header = _observation_header(header_observation, contact=contact)
            if header is not None:
                return verified_result(
                    header_observation,
                    header,
                    source="vision_roi_text",
                    roi_fastpath=True,
                    route="r5_header_roi",
                )

            # 2) Let a just-focused WebView paint and probe only the search band.
            # A cold first-frame OCR miss gets bounded text-only retries instead
            # of immediately loading Florence/YOLO over the whole window.
            search_observation = None
            search = None
            contact_target = None
            for attempt in range(retry_budget):
                if attempt:
                    time.sleep(settle)
                search_observation = _roi_observation(
                    computer, foreground_rect, purpose="search"
                )
                observations += 1
                perception.append(_performance_entry(search_observation))
                elements = list(search_observation.get("elements") or [])
                search = find_whatsapp_search_target(elements)
                contact_target = find_contact_target(
                    elements,
                    contact=contact,
                    search_rect=(search or {}).get("rect") if search else None,
                    foreground_rect=foreground_rect,
                )
                if search is not None or contact_target is not None:
                    break

            # 3) Accessibility is a cheap read-only rescue for the search field.
            # It may guide navigation, but visual evidence is still mandatory at
            # the end. We use it only before any state-changing ROI action.
            if search is None and contact_target is None:
                try:
                    uia_observation = _fresh_uia_observation(computer)
                    observations += 1
                    uia_elements = list(uia_observation.get("elements") or [])
                    search = find_whatsapp_search_target(uia_elements)
                    if search is not None:
                        search_observation = uia_observation
                except (RuntimeError, ValueError, OSError):
                    search = None

            # One final text-only top strip handles layouts where the search box
            # sits outside the narrow search band. This remains much cheaper than
            # full semantic parsing and is still read-only.
            if search is None and contact_target is None:
                time.sleep(settle)
                top_observation = _roi_observation(
                    computer, foreground_rect, purpose="top"
                )
                observations += 1
                perception.append(_performance_entry(top_observation))
                top_elements = list(top_observation.get("elements") or [])
                top_header = _observation_header(top_observation, contact=contact)
                if top_header is not None:
                    return verified_result(
                        top_observation,
                        top_header,
                        source="vision_roi_text",
                        roi_fastpath=True,
                        route="r5_top_roi_recovery",
                    )
                search = find_whatsapp_search_target(top_elements)
                contact_target = find_contact_target(
                    top_elements,
                    contact=contact,
                    search_rect=(search or {}).get("rect") if search else None,
                    foreground_rect=foreground_rect,
                )
                if search is not None or contact_target is not None:
                    search_observation = top_observation

            if contact_target is None and search is not None and search_observation is not None:
                typed = computer.action(
                    observation_id=str(search_observation.get("observation_id") or ""),
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
                        "roi": search_observation.get("roi_label") or "uia",
                    }
                )

                # After typing, do not retype automatically if OCR misses the
                # result. Only fresh read-only result observations are allowed.
                for attempt in range(retry_budget):
                    time.sleep(0.14 if attempt == 0 else settle)
                    result_observation = _roi_observation(
                        computer, foreground_rect, purpose="results"
                    )
                    observations += 1
                    perception.append(_performance_entry(result_observation))
                    result_elements = list(result_observation.get("elements") or [])
                    refreshed_search = find_whatsapp_search_target(result_elements)
                    search_rect = (
                        (refreshed_search or {}).get("rect")
                        or search.get("rect")
                        or {}
                    )
                    contact_target = find_contact_target(
                        result_elements,
                        contact=contact,
                        search_rect=search_rect,
                        foreground_rect=foreground_rect,
                    )
                    search_observation = result_observation
                    if contact_target is not None:
                        break

                if contact_target is None:
                    raise RuntimeError(
                        f"IRAS searched WhatsApp for {contact!r}, but bounded fresh "
                        "text-only result observations could not uniquely ground the "
                        "contact. The search input was not replayed and no message was sent."
                    )

            if contact_target is not None and search_observation is not None:
                clicked = computer.action(
                    observation_id=str(search_observation.get("observation_id") or ""),
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
                        "roi": search_observation.get("roi_label") or "uia",
                    }
                )

                # The click is never replayed. Verification retries are read-only.
                verification = None
                header = None
                for attempt in range(retry_budget + 1):
                    time.sleep(0.14 if attempt == 0 else settle)
                    verification = _roi_observation(
                        computer, foreground_rect, purpose="header"
                    )
                    observations += 1
                    perception.append(_performance_entry(verification))
                    header = _observation_header(verification, contact=contact)
                    if header is not None:
                        return verified_result(
                            verification,
                            header,
                            source="vision_roi_text",
                            roi_fastpath=True,
                            route="r5_search_results_header",
                        )

                # One broader read-only visual proof is permitted after a click,
                # but no further state-changing navigation action is allowed.
                verification = _fresh_visual_observation(computer)
                observations += 1
                header = _observation_header(verification, contact=contact)
                if header is not None:
                    return verified_result(
                        verification,
                        header,
                        source="vision",
                        roi_fastpath=False,
                        route="r5_readonly_header_broaden",
                    )
                raise RuntimeError(
                    f"WhatsApp navigation delivered one grounded click, but fresh "
                    f"visual evidence did not prove the chat header is {contact!r}. "
                    "The click was not replayed and no message was sent."
                )

            roi_failure_reason = "text-only ROI search/contact grounding remained inconclusive"
        except RuntimeError as exc:
            # Once a state-changing action has happened, RuntimeError is a fail-
            # closed outcome: do not fall into a route that could type/click again.
            if actions:
                raise
            roi_failure_reason = str(exc)
        except (ValueError, OSError) as exc:
            if actions:
                raise RuntimeError(
                    "WhatsApp ROI workflow stopped after a state-changing action; "
                    "IRAS will not replay it automatically."
                ) from exc
            roi_failure_reason = f"{type(exc).__name__}: {exc}"

    # R6 compatibility rescue remains text-first. A whole-foreground OCR pass is
    # much cheaper than Florence/YOLO and is semantically sufficient for a named
    # chat/search/header workflow. Full visual semantics are disabled by default
    # for WhatsApp and can be explicitly opted in for unusual icon-only layouts.
    foreground = computer._foreground()
    foreground_rect = foreground.get("rect") or {}
    try:
        observation = _roi_observation(computer, foreground_rect, purpose="workspace")
        observations += 1
        perception.append(_performance_entry(observation))
    except (RuntimeError, ValueError, OSError) as exc:
        observation = _fresh_uia_observation(computer)
        observations += 1
        roi_failure_reason = (roi_failure_reason + "; " if roi_failure_reason else "") + f"workspace_text: {type(exc).__name__}: {exc}"

    header = _observation_header(observation, contact=contact)
    if header is not None:
        result = verified_result(
            observation,
            header,
            source="vision_roi_text" if observation.get("capture_scope") == "roi" else "uia",
            roi_fastpath=bool(observation.get("capture_scope") == "roi"),
            route="r6_text_workspace_header",
        )
        result["roi_failure_reason"] = roi_failure_reason or None
        return result

    elements = list(observation.get("elements") or [])
    foreground_rect = (observation.get("foreground") or {}).get("rect") or foreground_rect
    search = find_whatsapp_search_target(elements)
    contact_target = find_contact_target(
        elements,
        contact=contact,
        search_rect=(search or {}).get("rect") if search else None,
        foreground_rect=foreground_rect,
    )

    if contact_target is None and search is None and _full_vision_fallback_enabled():
        observation = _fresh_visual_observation(computer)
        observations += 1
        elements = list(observation.get("elements") or [])
        foreground_rect = (observation.get("foreground") or {}).get("rect") or {}
        header = _observation_header(observation, contact=contact)
        if header is not None:
            result = verified_result(
                observation,
                header,
                source="vision",
                roi_fastpath=False,
                route="r6_opt_in_full_visual_scene",
            )
            result["roi_failure_reason"] = roi_failure_reason or None
            return result
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
        # After search typing, remain text-only. The state-changing type action
        # is never replayed and full visual semantics are not required to locate
        # a textual chat result.
        observation = _roi_observation(computer, foreground_rect, purpose="results")
        observations += 1
        perception.append(_performance_entry(observation))
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
            "the contact result. The search input was not replayed and no message was sent."
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

    verification = _roi_observation(computer, foreground_rect, purpose="header")
    observations += 1
    perception.append(_performance_entry(verification))
    header = _observation_header(verification, contact=contact)
    if header is None:
        time.sleep(0.35)
        verification = _roi_observation(computer, foreground_rect, purpose="header")
        observations += 1
        perception.append(_performance_entry(verification))
        header = _observation_header(verification, contact=contact)
    if header is None and _full_vision_fallback_enabled():
        verification = _fresh_visual_observation(computer)
        observations += 1
        header = _observation_header(verification, contact=contact)

    if header is None:
        raise RuntimeError(
            f"WhatsApp navigation completed, but fresh visual evidence did not "
            f"prove the chat header is {contact!r}. The click was not replayed "
            "and no message was sent."
        )

    result = verified_result(
        verification,
        header,
        source="vision_roi_text" if verification.get("capture_scope") == "roi" else "vision",
        roi_fastpath=bool(verification.get("capture_scope") == "roi"),
        route="r6_text_only_navigation",
    )
    result["roi_failure_reason"] = roi_failure_reason or None
    return result
