from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import time

import httpx

from iras.device_bridge.outcome_policy import (
    DEFAULT_MAX_RETRIES,
    ESCALATE_VISION,
    decide_outcome,
)


class UniversalComputerController:
    """Hybrid Windows computer-use controller.

    Observation uses Windows UI Automation first. When IRAS_OMNIPARSER_URL is
    configured, OmniParser can ground visual-only controls from a screenshot.
    Actions never accept free-form model coordinates: clicks/drags must refer
    to an element_id from a fresh observation.
    """

    ACTIONS = {
        "move",
        "click",
        "double_click",
        "right_click",
        "type_into",
        "press",
        "hotkey",
        "scroll",
        "drag",
        "wait",
    }

    VERIFY_CONDITIONS = {
        "element_exists",
        "element_absent",
        "text_contains",
        "window_title_contains",
        "screen_changed",
        "screen_stable",
        "visual_changed",
        "visual_stable",
        "foreground_changed",
    }

    UIA_ACTIONABLE_ROLES = {
        "button",
        "checkbox",
        "combobox",
        "dataitem",
        "edit",
        "hyperlink",
        "listitem",
        "menu",
        "menuitem",
        "radiobutton",
        "scrollbar",
        "slider",
        "spinner",
        "splitbutton",
        "tab",
        "tabitem",
        "textbox",
        "treeitem",
    }

    # UIA frequently exposes framework plumbing as keyboard-focusable panes.
    # Those nodes can accept focus without representing a user-operable control,
    # which would incorrectly suppress visual grounding in auto mode.
    UIA_PASSIVE_ROLES = {
        "document",
        "group",
        "pane",
        "separator",
        "statusbar",
        "text",
        "titlebar",
        "toolbar",
        "window",
    }

    UIA_INFRASTRUCTURE_LABELS = (
        "non client input sink window",
        "input sink window",
        "desktop window",
        "default ime",
        "msctfime ui",
        "olemainthreadwndname",
    )

    CAPTURE_KEEP_LIMIT = 80

    BLOCKED_VISUAL_LABELS = (
        "diskpart",
        "registry editor",
        "group policy",
        "local security policy",
        "command prompt",
        "powershell",
        "windows terminal",
        "task scheduler",
        "services console",
        "reset this pc",
        "factory reset",
        "format disk",
        "format drive",
        "disable windows defender",
        "turn off windows defender",
        "disable antivirus",
        "turn off firewall",
        "user account control",
        "delete account",
        "remove account",
    )

    def __init__(self, ui, visual):
        self.ui = ui
        self.visual = visual
        self._observations: dict[str, dict] = {}
        self._observation_order: list[str] = []
        self._verification_failures: dict[str, int] = {}

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(
            str(value or "")
            .strip()
            .lower()
            .replace("_", " ")
            .replace("-", " ")
            .split()
        )

    def _require_windows(self) -> None:
        if os.name != "nt":
            raise RuntimeError(
                "Universal computer control is only available on Windows."
            )

    def _user32(self):
        self._require_windows()
        return ctypes.windll.user32

    def _desktop_rect(self) -> dict:
        user32 = self._user32()
        # Virtual desktop metrics include secondary monitors and negative origins.
        left = int(user32.GetSystemMetrics(76))
        top = int(user32.GetSystemMetrics(77))
        width = int(user32.GetSystemMetrics(78))
        height = int(user32.GetSystemMetrics(79))

        if width <= 0 or height <= 0:
            left = 0
            top = 0
            width = int(user32.GetSystemMetrics(0))
            height = int(user32.GetSystemMetrics(1))

        return {
            "left": left,
            "top": top,
            "width": width,
            "height": height,
            "right": left + width,
            "bottom": top + height,
        }

    def _foreground(self) -> dict:
        user32 = self._user32()
        hwnd = int(user32.GetForegroundWindow() or 0)
        title = ""

        if hwnd:
            length = int(user32.GetWindowTextLengthW(hwnd) or 0)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value

        rect = None
        if hwnd:
            native = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(native)):
                rect = {
                    "left": int(native.left),
                    "top": int(native.top),
                    "width": int(native.right - native.left),
                    "height": int(native.bottom - native.top),
                }

        return {
            "hwnd": hwnd,
            "title": title,
            "rect": rect,
        }

    def _cursor(self) -> dict:
        point = wintypes.POINT()
        if not self._user32().GetCursorPos(ctypes.byref(point)):
            return {"x": None, "y": None}
        return {"x": int(point.x), "y": int(point.y)}

    @staticmethod
    def _capture_root() -> Path:
        root = Path.home() / ".iras" / "computer_use"
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def _prune_capture_files(
        cls,
        root: Path | None = None,
        *,
        keep: int | None = None,
        max_age_seconds: float = 86400.0,
    ) -> None:
        """Bound local screenshot artifacts so computer-use does not leak disk space."""
        try:
            root = Path(root) if root is not None else cls._capture_root()
            if not root.exists():
                return
            keep = max(12, int(keep or cls.CAPTURE_KEEP_LIMIT))
            now = time.time()
            candidates = [
                item
                for item in root.iterdir()
                if item.is_file()
                and item.name.startswith(("desktop-", "foreground-", "omniparser-"))
            ]
            candidates.sort(
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            for index, item in enumerate(candidates):
                age = now - float(item.stat().st_mtime)
                if index >= keep or age > max_age_seconds:
                    try:
                        item.unlink()
                    except OSError:
                        pass
        except OSError:
            # Capture cleanup is maintenance only and must never break control.
            pass

    def _capture_desktop(self) -> dict:
        from PIL import ImageGrab

        desktop = self._desktop_rect()
        try:
            image = ImageGrab.grab(all_screens=True)
        except TypeError:
            image = ImageGrab.grab()

        original_width, original_height = image.size

        max_width = max(
            800,
            min(
                int(os.getenv("IRAS_COMPUTER_VISION_MAX_WIDTH", "1600")),
                2560,
            ),
        )
        max_height = max(
            600,
            min(
                int(os.getenv("IRAS_COMPUTER_VISION_MAX_HEIGHT", "1200")),
                1600,
            ),
        )

        vision_image = image.copy()
        vision_image.thumbnail((max_width, max_height))

        root = self._capture_root()
        stamp = str(int(time.time() * 1000))
        target = root / f"desktop-{stamp}.jpg"

        vision_image.convert("RGB").save(
            target,
            "JPEG",
            quality=82,
            optimize=True,
        )

        digest = hashlib.sha256(target.read_bytes()).hexdigest()

        return {
            "path": str(target),
            "sha256": digest,
            "bytes": target.stat().st_size,
            "image_width": int(vision_image.width),
            "image_height": int(vision_image.height),
            "source_width": int(original_width),
            "source_height": int(original_height),
            "desktop_rect": desktop,
            "capture_scope": "desktop",
        }

    def _capture_foreground(self, window_rect: dict) -> dict:
        """Capture the foreground window for high-resolution vision."""
        from PIL import ImageGrab
        desktop = self._desktop_rect()
        try:
            image = ImageGrab.grab(all_screens=True)
        except TypeError:
            image = ImageGrab.grab()
        desktop_left = int(desktop.get("left", 0) or 0)
        desktop_top = int(desktop.get("top", 0) or 0)
        requested_left = int(window_rect.get("left", desktop_left) or desktop_left)
        requested_top = int(window_rect.get("top", desktop_top) or desktop_top)
        requested_width = max(1, int(window_rect.get("width", image.width) or image.width))
        requested_height = max(1, int(window_rect.get("height", image.height) or image.height))
        crop_left = max(0, requested_left - desktop_left)
        crop_top = max(0, requested_top - desktop_top)
        crop_right = min(
            image.width,
            requested_left + requested_width - desktop_left,
        )
        crop_bottom = min(
            image.height,
            requested_top + requested_height - desktop_top,
        )
        if crop_right <= crop_left or crop_bottom <= crop_top:
            raise RuntimeError(
                "Foreground window rectangle is outside captured desktop."
            )
        cropped = image.crop(
            (crop_left, crop_top, crop_right, crop_bottom)
        )
        source_width, source_height = cropped.size
        max_width = max(
            800,
            min(
                int(os.getenv("IRAS_COMPUTER_VISION_MAX_WIDTH", "1600")),
                2560,
            ),
        )
        max_height = max(
            600,
            min(
                int(os.getenv("IRAS_COMPUTER_VISION_MAX_HEIGHT", "1200")),
                1600,
            ),
        )
        vision_image = cropped.copy()
        vision_image.thumbnail((max_width, max_height))
        root = self._capture_root()
        target = root / f"foreground-{int(time.time() * 1000)}.png"
        vision_image.convert("RGB").save(target, "PNG", optimize=True)
        region_rect = {
            "left": desktop_left + crop_left,
            "top": desktop_top + crop_top,
            "width": crop_right - crop_left,
            "height": crop_bottom - crop_top,
        }
        return {
            "path": str(target),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "bytes": target.stat().st_size,
            "image_width": int(vision_image.width),
            "image_height": int(vision_image.height),
            "source_width": int(source_width),
            "source_height": int(source_height),
            "desktop_rect": region_rect,
            "capture_scope": "foreground",
        }
    @staticmethod
    def _rect_center(rect: dict) -> tuple[int, int]:
        return (
            int(rect.get("left", 0)) + int(rect.get("width", 0)) // 2,
            int(rect.get("top", 0)) + int(rect.get("height", 0)) // 2,
        )

    @classmethod
    def _uia_elements(cls, snapshot: dict) -> list[dict]:
        output = []
        for index, raw in enumerate(snapshot.get("elements", []) or []):
            if not isinstance(raw, dict):
                continue
            rect = raw.get("rect") or {}
            width = int(rect.get("width", 0) or 0)
            height = int(rect.get("height", 0) or 0)
            if width <= 0 or height <= 0:
                continue
            normalized_rect = {
                "left": int(rect.get("left", 0) or 0),
                "top": int(rect.get("top", 0) or 0),
                "width": width,
                "height": height,
            }
            x, y = cls._rect_center(normalized_rect)
            name = str(raw.get("name") or "").strip()
            automation_id = str(raw.get("automation_id") or "").strip()
            role = str(raw.get("role") or "").strip()
            enabled = bool(raw.get("enabled", True))
            focusable = bool(raw.get("focusable", False))
            label = name or automation_id or role or "UI element"
            role_key = role.casefold()
            semantic = cls._normalize(" ".join((name, automation_id, label)))
            compact = semantic.replace(" ", "")
            infrastructure = any(
                term in semantic for term in cls.UIA_INFRASTRUCTURE_LABELS
            )
            interactive = bool(
                enabled
                and not infrastructure
                and (
                    role_key in cls.UIA_ACTIONABLE_ROLES
                    or (
                        focusable
                        and role_key not in cls.UIA_PASSIVE_ROLES
                        and bool(semantic)
                        and not compact.isdigit()
                    )
                )
            )
            output.append(
                {
                    "element_id": f"uia:{index}",
                    "source": "uia",
                    "label": label,
                    "name": name,
                    "automation_id": automation_id,
                    "role": role,
                    "value": raw.get("value"),
                    "enabled": enabled,
                    "focusable": focusable,
                    "interactive": interactive,
                    "rect": normalized_rect,
                    "center": {"x": x, "y": y},
                }
            )
        return output

    @classmethod
    def _uia_has_actionable_elements(cls, elements: list[dict]) -> bool:
        """Return True only when UIA exposes meaningful action targets.

        Some Windows/Electron/WinUI apps expose internal focus sinks as a
        focusable ``Pane``. Treating those framework nodes as actionable makes
        auto vision believe accessibility is sufficient even though no real
        control can be grounded. Explicit control roles remain authoritative;
        focusable custom controls are accepted only when their semantic label is
        meaningful and they are not passive framework containers.
        """
        for element in elements or []:
            if not isinstance(element, dict):
                continue
            if not bool(element.get("enabled", True)):
                continue

            role = str(element.get("role") or "").strip().casefold()
            semantic = cls._normalize(
                " ".join(
                    str(element.get(key) or "")
                    for key in ("name", "automation_id", "label")
                )
            )
            compact = semantic.replace(" ", "")

            if any(term in semantic for term in cls.UIA_INFRASTRUCTURE_LABELS):
                continue

            if role in cls.UIA_ACTIONABLE_ROLES:
                return True

            if not bool(element.get("interactive", False)):
                continue
            if role in cls.UIA_PASSIVE_ROLES:
                continue
            if semantic and not compact.isdigit():
                return True

        return False
    @staticmethod
    def _normalize_vision_elements(
        parsed: list,
        *,
        desktop_rect: dict,
        image_width: int,
        image_height: int,
    ) -> list[dict]:
        output = []
        left = int(desktop_rect.get("left", 0) or 0)
        top = int(desktop_rect.get("top", 0) or 0)
        desktop_width = max(1, int(desktop_rect.get("width", 1) or 1))
        desktop_height = max(1, int(desktop_rect.get("height", 1) or 1))
        image_width = max(1, int(image_width or 1))
        image_height = max(1, int(image_height or 1))

        for index, raw in enumerate(parsed or []):
            if not isinstance(raw, dict):
                continue

            bbox = raw.get("bbox") or raw.get("coordinates") or raw.get("box")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue

            try:
                x1, y1, x2, y2 = [float(value) for value in bbox]
            except (TypeError, ValueError):
                continue

            # Official OmniParser returns ratio xyxy. Also accept absolute
            # image-pixel boxes from compatible endpoints.
            if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 1.5:
                px1 = left + int(round(x1 * desktop_width))
                py1 = top + int(round(y1 * desktop_height))
                px2 = left + int(round(x2 * desktop_width))
                py2 = top + int(round(y2 * desktop_height))
            else:
                px1 = left + int(round((x1 / image_width) * desktop_width))
                py1 = top + int(round((y1 / image_height) * desktop_height))
                px2 = left + int(round((x2 / image_width) * desktop_width))
                py2 = top + int(round((y2 / image_height) * desktop_height))

            if px2 <= px1 or py2 <= py1:
                continue

            rect = {
                "left": px1,
                "top": py1,
                "width": px2 - px1,
                "height": py2 - py1,
            }
            center_x = px1 + (px2 - px1) // 2
            center_y = py1 + (py2 - py1) // 2
            content = str(raw.get("content") or raw.get("text") or "").strip()
            role = str(raw.get("type") or raw.get("role") or "visual").strip()
            label = content or role or "visual element"

            output.append(
                {
                    "element_id": f"vision:{index}",
                    "source": "omniparser",
                    "label": label,
                    "name": content,
                    "automation_id": "",
                    "role": role,
                    "value": None,
                    "enabled": True,
                    "interactive": bool(raw.get("interactivity", True)),
                    "rect": rect,
                    "center": {"x": center_x, "y": center_y},
                    "vision_source": str(raw.get("source") or ""),
                }
            )

        return output

    @staticmethod
    def _omniparser_endpoint() -> str:
        raw = os.getenv("IRAS_OMNIPARSER_URL", "").strip()
        if not raw:
            return ""
        raw = raw.rstrip("/")
        if raw.endswith("/parse"):
            return raw + "/"
        return raw + "/parse/"

    @staticmethod
    def _omniparser_probe_url() -> str:
        raw = os.getenv("IRAS_OMNIPARSER_URL", "").strip().rstrip("/")
        if not raw:
            return ""
        if raw.endswith("/parse"):
            raw = raw[:-6].rstrip("/")
        return raw + "/probe/"

    @staticmethod
    def _omniparser_headers() -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = os.getenv("IRAS_OMNIPARSER_API_KEY", "").strip()
        if key:
            headers["Authorization"] = "Bearer " + key
        return headers

    def _run_omniparser(self, screenshot: dict) -> dict:
        endpoint = self._omniparser_endpoint()
        if not endpoint:
            return {
                "status": "disabled",
                "available": False,
                "elements": [],
                "reason": "IRAS_OMNIPARSER_URL is not configured.",
            }

        payload = base64.b64encode(
            Path(screenshot["path"]).read_bytes()
        ).decode("ascii")

        timeout = max(
            10.0,
            min(
                float(os.getenv("IRAS_OMNIPARSER_TIMEOUT", "120")),
                300.0,
            ),
        )

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    endpoint,
                    json={"base64_image": payload},
                    headers=self._omniparser_headers(),
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return {
                "status": "error",
                "available": False,
                "elements": [],
                "reason": f"{type(exc).__name__}: {exc}",
            }

        parsed = data.get("parsed_content_list")
        if not isinstance(parsed, list):
            parsed = data.get("elements")
        if not isinstance(parsed, list):
            parsed = []

        elements = self._normalize_vision_elements(
            parsed,
            desktop_rect=screenshot["desktop_rect"],
            image_width=int(screenshot["image_width"]),
            image_height=int(screenshot["image_height"]),
        )

        annotated = None
        som = data.get("som_image_base64")
        if isinstance(som, str) and som.strip():
            try:
                raw = base64.b64decode(som)
                target = (
                    self._capture_root()
                    / f"omniparser-{int(time.time() * 1000)}.png"
                )
                target.write_bytes(raw)
                annotated = {
                    "path": str(target),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                }
            except Exception:
                annotated = None

        return {
            "status": "available",
            "available": True,
            "elements": elements,
            "element_count": len(elements),
            "latency": data.get("latency"),
            "annotated_screenshot": annotated,
        }

    def _save_observation(self, observation: dict) -> None:
        observation_id = str(observation["observation_id"])
        self._observations[observation_id] = observation
        self._observation_order.append(observation_id)
        while len(self._observation_order) > 12:
            expired = self._observation_order.pop(0)
            self._observations.pop(expired, None)

    def status(self) -> dict:
        endpoint = self._omniparser_endpoint()
        result = {
            "windows": os.name == "nt",
            "uia": os.name == "nt",
            "omniparser_configured": bool(endpoint),
            "omniparser_endpoint": endpoint or None,
            "omniparser_available": False,
            "hybrid_mode": True,
            "coordinate_policy": "fresh_observation_element_ids_only",
            "foreground_freshness_guard": True,
            "actions": sorted(self.ACTIONS),
            "verification_conditions": sorted(self.VERIFY_CONDITIONS),
            "vision_scopes": ["auto", "foreground", "desktop"],
        }

        if not endpoint:
            result["omniparser_status"] = "disabled"
            return result

        probe = self._omniparser_probe_url()
        timeout = max(
            2.0,
            min(float(os.getenv("IRAS_OMNIPARSER_PROBE_TIMEOUT", "4")), 15.0),
        )
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(probe, headers=self._omniparser_headers())
                response.raise_for_status()
            result["omniparser_available"] = True
            result["omniparser_status"] = "ready"
        except Exception as exc:
            result["omniparser_status"] = "unreachable"
            result["omniparser_error"] = f"{type(exc).__name__}: {exc}"

        return result

    def observe(
        self,
        *,
        vision: str = "auto",
        scope: str = "auto",
        max_elements: int = 180,
    ) -> dict:
        self._require_windows()
        vision = str(vision or "auto").strip().lower()
        if vision not in {"off", "auto", "always"}:
            raise ValueError("vision must be off, auto, or always.")
        scope = str(scope or "auto").strip().lower()
        if scope not in {"auto", "foreground", "desktop"}:
            raise ValueError("scope must be auto, foreground, or desktop.")

        max_elements = max(1, min(int(max_elements), 300))
        screenshot = self._capture_desktop()
        foreground = self._foreground()

        uia_snapshot = {}
        uia_error = ""
        if foreground["hwnd"]:
            try:
                uia_snapshot = self.visual._run_uia_observer(
                    int(foreground["hwnd"]),
                    max_elements,
                )
            except Exception as exc:
                uia_error = f"{type(exc).__name__}: {exc}"

        uia_elements = self._uia_elements(uia_snapshot)
        uia_available = bool(uia_elements)
        uia_actionable = self._uia_has_actionable_elements(
            uia_elements
        )
        should_run_vision = (
            vision == "always"
            or (
                vision == "auto"
                and bool(self._omniparser_endpoint())
                and (scope == "desktop" or not uia_actionable)
            )
        )

        vision_result = {
            "status": "not_requested" if vision == "off" else "not_needed",
            "available": False,
            "elements": [],
        }
        vision_capture = None
        vision_scope = None
        if should_run_vision:
            foreground_rect = foreground.get("rect") or {}
            if scope == "desktop":
                vision_capture = screenshot
                vision_scope = "desktop"
            else:
                try:
                    if (
                        int(foreground_rect.get("width", 0) or 0) > 0
                        and int(foreground_rect.get("height", 0) or 0) > 0
                    ):
                        vision_capture = self._capture_foreground(
                            foreground_rect
                        )
                        vision_scope = "foreground"
                    else:
                        vision_capture = screenshot
                        vision_scope = "desktop"
                except Exception:
                    vision_capture = screenshot
                    vision_scope = "desktop"
            vision_result = self._run_omniparser(vision_capture)
        elif vision != "off" and not self._omniparser_endpoint():
            vision_result = {
                "status": "disabled",
                "available": False,
                "elements": [],
                "reason": "IRAS_OMNIPARSER_URL is not configured.",
            }

        elements = list(uia_elements)
        elements.extend(vision_result.get("elements", []) or [])

        visual_capture = vision_capture or screenshot
        compact = {
            "screen_sha256": screenshot["sha256"],
            "visual_sha256": visual_capture.get("sha256"),
            "vision_scope": vision_scope,
            "foreground_hwnd": foreground["hwnd"],
            "foreground_title": foreground["title"],
            "elements": [
                (
                    element.get("element_id"),
                    element.get("label"),
                    element.get("role"),
                    element.get("rect"),
                )
                for element in elements
            ],
        }
        observation_id = hashlib.sha256(
            json.dumps(
                compact,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:24]

        output = {
            "observation_id": observation_id,
            "captured_at": time.time(),
            "foreground": foreground,
            "cursor": self._cursor(),
            "screenshot": screenshot,
            "uia_available": uia_available,
            "uia_actionable": uia_actionable,
            "uia_status": "available" if uia_available else "unavailable",
            "uia_error": uia_error or None,
            "uia_element_count": len(uia_elements),
            "vision_requested": vision,
            "observation_scope": scope,
            "vision_scope": vision_scope,
            "vision_capture": vision_capture,
            "visual_sha256": visual_capture.get("sha256"),
            "vision_available": bool(vision_result.get("available")),
            "vision_status": vision_result.get("status"),
            "vision_reason": vision_result.get("reason"),
            "vision_element_count": len(vision_result.get("elements", []) or []),
            "annotated_screenshot": vision_result.get("annotated_screenshot"),
            "element_count": len(elements),
            "elements": elements,
            "action_policy": (
                "Use only element_id values from this observation. "
                "Do not invent raw click coordinates. Re-observe if the "
                "foreground window changes before acting."
            ),
        }
        self._save_observation(output)
        self._prune_capture_files()
        return output

    def _observation(self, observation_id: str) -> dict:
        observation_id = str(observation_id or "").strip()
        observation = self._observations.get(observation_id)
        if observation is None:
            raise RuntimeError(
                "The computer observation is missing or stale. Re-observe the "
                "screen before acting."
            )

        ttl = max(
            5.0,
            min(float(os.getenv("IRAS_COMPUTER_OBSERVATION_TTL", "30")), 120.0),
        )
        if str(observation.get("observation_scope") or "auto").lower() == "desktop":
            ttl = min(ttl, 10.0)
        age = time.time() - float(observation.get("captured_at", 0) or 0)
        if age > ttl:
            raise RuntimeError(
                "The computer observation is too old to act on safely. "
                "Re-observe the screen first."
            )
        return observation

    @staticmethod
    def _element(observation: dict, element_id: str) -> dict:
        wanted = str(element_id or "").strip()
        if not wanted:
            raise ValueError("This action requires an element_id.")
        for element in observation.get("elements", []) or []:
            if str(element.get("element_id") or "") == wanted:
                return element
        raise RuntimeError(
            "The requested element_id is not present in that observation. "
            "Re-observe instead of guessing a coordinate."
        )

    @classmethod
    def _blocked_element(cls, element: dict) -> bool:
        label = cls._normalize(
            " ".join(
                str(element.get(key) or "")
                for key in ("label", "name", "automation_id", "role")
            )
        )
        return any(term in label for term in cls.BLOCKED_VISUAL_LABELS)

    def _set_cursor(self, x: int, y: int) -> None:
        desktop = self._desktop_rect()
        if not (
            desktop["left"] <= int(x) < desktop["right"]
            and desktop["top"] <= int(y) < desktop["bottom"]
        ):
            raise ValueError("Grounded cursor target is outside the virtual desktop.")
        user32 = self._user32()
        try:
            moved = bool(user32.SetPhysicalCursorPos(int(x), int(y)))
        except Exception:
            moved = bool(user32.SetCursorPos(int(x), int(y)))
        if not moved:
            raise RuntimeError("Windows refused to move the cursor.")

    def _mouse_click(self, x: int, y: int, *, button: str = "left", count: int = 1) -> None:
        self._set_cursor(x, y)
        user32 = self._user32()
        if button == "right":
            down, up = 0x0008, 0x0010
        else:
            down, up = 0x0002, 0x0004
        for index in range(max(1, min(int(count), 2))):
            user32.mouse_event(down, 0, 0, 0, 0)
            time.sleep(0.035)
            user32.mouse_event(up, 0, 0, 0, 0)
            if index + 1 < count:
                time.sleep(0.08)

    def _drag(self, source: tuple[int, int], target: tuple[int, int]) -> None:
        self._set_cursor(*source)
        user32 = self._user32()
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        try:
            steps = 12
            for step in range(1, steps + 1):
                ratio = step / steps
                x = int(round(source[0] + ((target[0] - source[0]) * ratio)))
                y = int(round(source[1] + ((target[1] - source[1]) * ratio)))
                self._set_cursor(x, y)
                time.sleep(0.025)
        finally:
            user32.mouse_event(0x0004, 0, 0, 0, 0)

    def _foreground_still_matches(self, observation: dict) -> bool:
        previous = observation.get("foreground") or {}
        current = self._foreground()
        previous_hwnd = int(previous.get("hwnd", 0) or 0)
        current_hwnd = int(current.get("hwnd", 0) or 0)
        if previous_hwnd != current_hwnd:
            return False

        previous_rect = previous.get("rect") or {}
        current_rect = current.get("rect") or {}
        if previous_rect and current_rect:
            for key in ("left", "top", "width", "height"):
                before = int(previous_rect.get(key, 0) or 0)
                after = int(current_rect.get(key, 0) or 0)
                if abs(before - after) > 2:
                    return False
        return True

    def _require_fresh_foreground(self, observation: dict) -> None:
        if not self._foreground_still_matches(observation):
            raise RuntimeError(
                "The foreground window changed after observation. Re-observe "
                "before injecting mouse or keyboard input."
            )

    def action(
        self,
        *,
        observation_id: str,
        action: str,
        element_id: str = "",
        target_element_id: str = "",
        text: str = "",
        key: str = "",
        keys: list[str] | None = None,
        amount: int = 0,
        replace: bool = False,
        seconds: float = 0.5,
        verify: bool = True,
    ) -> dict:
        observation = self._observation(observation_id)
        action = str(action or "").strip().lower()
        if action not in self.ACTIONS:
            raise PermissionError(f"Computer action '{action}' is not allowed.")

        selected = None
        target = None
        point = None
        target_point = None

        if action in {
            "move", "click", "double_click", "right_click", "type_into", "drag"
        }:
            selected = self._element(observation, element_id)
            if self._blocked_element(selected):
                raise PermissionError(
                    "That visual target is a blocked administrative/security control."
                )
            point = self._rect_center(selected["rect"])

        if action == "drag":
            target = self._element(observation, target_element_id)
            if self._blocked_element(target):
                raise PermissionError(
                    "That visual drag target is a blocked administrative/security control."
                )
            target_point = self._rect_center(target["rect"])

        if action != "wait":
            self._require_fresh_foreground(observation)

        if action == "move":
            self._set_cursor(*point)
        elif action == "click":
            self._mouse_click(*point)
        elif action == "double_click":
            self._mouse_click(*point, count=2)
        elif action == "right_click":
            self._mouse_click(*point, button="right")
        elif action == "type_into":
            value = str(text or "")
            if not value:
                raise ValueError("type_into requires non-empty text.")
            if "\x00" in value or len(value) > 4000:
                raise PermissionError("Typed text is outside the allowed bounds.")
            self._mouse_click(*point)
            time.sleep(0.08)
            self._require_fresh_foreground(observation)
            if replace:
                self.ui.hotkey(["ctrl", "a"])
                time.sleep(0.05)
            self.ui.type_text(value)
        elif action == "press":
            self.ui._key_code(key)
            self.ui.press(key)
        elif action == "hotkey":
            normalized = [str(item).strip().lower() for item in (keys or [])]
            if not (2 <= len(normalized) <= 3):
                raise ValueError("hotkey requires 2 or 3 keys.")
            if any(item in {"win", "windows", "meta"} for item in normalized):
                raise PermissionError("Windows-key shortcuts are not allowed.")
            key_set = set(normalized)
            if {"ctrl", "alt", "delete"}.issubset(key_set):
                raise PermissionError("Ctrl+Alt+Delete is not allowed.")
            if "alt" in key_set and "f4" in key_set:
                raise PermissionError("Alt+F4 is not allowed through computer vision.")
            for item in normalized:
                self.ui._key_code(item)
            self.ui.hotkey(normalized)
        elif action == "scroll":
            amount = int(amount)
            if amount == 0 or not (-10 <= amount <= 10):
                raise ValueError("scroll amount must be between -10 and 10 and non-zero.")
            if element_id:
                selected = self._element(observation, element_id)
                if self._blocked_element(selected):
                    raise PermissionError(
                        "That visual scroll target is a blocked administrative/security control."
                    )
                point = self._rect_center(selected["rect"])
                self._set_cursor(*point)
            self.ui.scroll(amount)
        elif action == "drag":
            self._drag(point, target_point)
        elif action == "wait":
            seconds = float(seconds)
            if not (0.05 <= seconds <= 5.0):
                raise ValueError("wait must be between 0.05 and 5 seconds.")
            time.sleep(seconds)

        time.sleep(0.25)

        after = None
        if verify:
            after = self.observe(
                vision=str(observation.get("vision_requested") or "auto"),
                scope=str(observation.get("observation_scope") or "auto"),
                max_elements=180,
            )

        result = {
            "action": action,
            "observation_id": observation_id,
            "selected_element": selected,
            "target_element": target,
            "derived_point": (
                {"x": point[0], "y": point[1]} if point else None
            ),
            "derived_target_point": (
                {"x": target_point[0], "y": target_point[1]}
                if target_point else None
            ),
            "input_injected": action != "wait",
            "action_verified": bool(after),
            "closed_loop_observed": bool(after),
            "goal_verified": False,
            "verification_observation": after,
        }

        if after:
            state_delta = self._state_delta(after, observation)
            result["screen_changed"] = state_delta["screen_changed"]
            result["foreground_changed"] = state_delta["foreground_changed"]
            result["visual_changed"] = state_delta["visual_changed"]

            any_state_change = bool(
                state_delta["screen_changed"]
                or state_delta["visual_changed"]
                or state_delta["foreground_changed"]
            )
            result["delivery_assessment"] = {
                "result": "observed",
                "confidence": 0.90 if any_state_change else 0.68,
                "confidence_label": "high" if any_state_change else "medium",
                "state_delta": state_delta,
                "semantic_goal_verified": False,
                "reason_codes": [
                    "post_action_state_change_observed"
                    if any_state_change
                    else "post_action_observation_without_visible_change",
                    "semantic_goal_requires_computer_verify",
                ],
            }
        else:
            result["delivery_assessment"] = {
                "result": "not_observed",
                "confidence": 0.0,
                "confidence_label": "low",
                "state_delta": {
                    "available": False,
                    "screen_changed": None,
                    "visual_changed": None,
                    "foreground_changed": None,
                },
                "semantic_goal_verified": False,
                "reason_codes": ["closed_loop_observation_disabled"],
            }

        return result

    @classmethod
    def _vision_row_haystack(cls, observation: dict) -> list[str]:
        """Reconstruct text lines that OmniParser split into adjacent elements.

        OCR/OmniParser commonly emits a single visible sentence as several
        neighboring text boxes. Semantic verification must not require the
        whole sentence to live inside one box, but it also must not concatenate
        unrelated text from different parts of the screen. We therefore join
        only visual elements whose vertical centers belong to the same row.
        """
        visual = []
        for element in observation.get("elements", []) or []:
            if not isinstance(element, dict):
                continue
            element_id = str(element.get("element_id") or "")
            source = str(element.get("source") or "").casefold()
            if source != "vision" and not element_id.startswith("vision:"):
                continue

            rect = element.get("rect") or {}
            try:
                left = int(rect.get("left", 0) or 0)
                top = int(rect.get("top", 0) or 0)
                width = int(rect.get("width", 0) or 0)
                height = int(rect.get("height", 0) or 0)
            except (TypeError, ValueError):
                continue
            if width <= 0 or height <= 0:
                continue

            text = cls._normalize(
                " ".join(
                    str(element.get(key) or "")
                    for key in ("label", "name", "value")
                )
            )
            if not text:
                continue
            visual.append(
                {
                    "left": left,
                    "center_y": top + (height / 2.0),
                    "height": height,
                    "text": text,
                }
            )

        visual.sort(key=lambda item: (item["center_y"], item["left"]))
        rows: list[dict] = []
        for item in visual:
            best = None
            best_distance = None
            for row in rows:
                distance = abs(float(item["center_y"]) - float(row["center_y"]))
                tolerance = max(8.0, min(22.0, (item["height"] + row["height"]) * 0.55))
                if distance <= tolerance and (best_distance is None or distance < best_distance):
                    best = row
                    best_distance = distance
            if best is None:
                rows.append(
                    {
                        "center_y": float(item["center_y"]),
                        "height": float(item["height"]),
                        "items": [item],
                    }
                )
            else:
                best["items"].append(item)
                count = len(best["items"])
                best["center_y"] = (
                    (best["center_y"] * (count - 1)) + float(item["center_y"])
                ) / count
                best["height"] = max(float(best["height"]), float(item["height"]))

        values = []
        for row in rows:
            items = sorted(row["items"], key=lambda item: item["left"])
            joined = cls._normalize(" ".join(item["text"] for item in items))
            if joined:
                values.append(joined)
        return values

    @classmethod
    def _element_haystack(cls, observation: dict) -> list[str]:
        values = []
        for element in observation.get("elements", []) or []:
            combined = " ".join(
                str(element.get(key) or "")
                for key in ("label", "name", "automation_id", "role", "value")
            )
            normalized = cls._normalize(combined)
            if normalized:
                values.append(normalized)

        # Add line-level visual reconstructions after individual elements. This
        # preserves existing matching behavior while allowing phrases split by
        # OCR into adjacent boxes to verify as one visible sentence.
        values.extend(cls._vision_row_haystack(observation))
        return list(dict.fromkeys(values))

    @staticmethod
    def _visual_hash(observation: dict) -> str:
        return str(
            observation.get("visual_sha256")
            or (observation.get("vision_capture") or {}).get("sha256")
            or (observation.get("screenshot") or {}).get("sha256")
            or ""
        )

    @classmethod
    def _state_delta(cls, observation: dict, prior: dict | None) -> dict:
        """Return low-level state-change evidence without claiming goal success."""
        if not prior:
            return {
                "available": False,
                "screen_changed": None,
                "visual_changed": None,
                "foreground_changed": None,
            }

        return {
            "available": True,
            "screen_changed": (
                observation.get("screenshot", {}).get("sha256")
                != prior.get("screenshot", {}).get("sha256")
            ),
            "visual_changed": (
                cls._visual_hash(observation) != cls._visual_hash(prior)
            ),
            "foreground_changed": (
                observation.get("foreground", {}).get("hwnd")
                != prior.get("foreground", {}).get("hwnd")
            ),
        }

    @classmethod
    def _verification_assessment(
        cls,
        *,
        condition: str,
        status: str,
        evidence: dict,
        observation: dict,
        prior: dict | None,
        vision_escalated: bool,
    ) -> dict:
        """Classify verification strength separately from raw state change.

        A changed screenshot proves that *something* changed, not that the user's
        requested end state was achieved.  This assessment keeps those concepts
        separate while preserving the existing PASS/FAIL contract.
        """
        semantic_conditions = {"element_exists", "element_absent", "text_contains"}
        state_change_conditions = {
            "screen_changed",
            "visual_changed",
            "foreground_changed",
        }
        stability_conditions = {"screen_stable", "visual_stable"}

        state_delta = cls._state_delta(observation, prior)
        element_ids = [
            str(item.get("element_id") or "")
            for item in (observation.get("elements") or [])
        ]
        sources = []
        if any(value.startswith("uia:") for value in element_ids):
            sources.append("uia")
        if bool(observation.get("vision_available")) or any(
            value.startswith("vision:") for value in element_ids
        ):
            sources.append("vision")

        verified = status == "PASS"
        reason_codes: list[str] = []

        if status == "INCONCLUSIVE":
            confidence = 0.20
            outcome_class = "inconclusive"
            reason_codes.append("verification_inconclusive")
        elif condition in semantic_conditions:
            outcome_class = "semantic_goal"
            if condition == "element_absent":
                if "vision" in sources:
                    confidence = 0.97 if verified else 0.94
                    reason_codes.append("semantic_absence_checked_with_vision")
                else:
                    confidence = 0.72 if verified else 0.78
                    reason_codes.append("semantic_absence_without_visual_coverage")
            else:
                confidence = 0.98 if "vision" in sources else 0.93
                if verified:
                    reason_codes.append("semantic_match_found")
                else:
                    reason_codes.append("semantic_match_not_found")
            if vision_escalated:
                reason_codes.append("vision_escalated_for_target_verification")
        elif condition == "window_title_contains":
            outcome_class = "window_state_goal"
            confidence = 0.99 if verified else 0.96
            sources = ["foreground_title"]
            reason_codes.append(
                "window_title_matched" if verified else "window_title_not_matched"
            )
        elif condition in state_change_conditions:
            outcome_class = "state_transition"
            confidence = 0.90 if verified else 0.88
            reason_codes.append(
                "state_transition_observed" if verified else "state_transition_not_observed"
            )
            if condition == "screen_changed":
                sources = ["screenshot_hash"]
            elif condition == "visual_changed":
                sources = ["visual_hash"]
            else:
                sources = ["foreground_window"]
        elif condition in stability_conditions:
            outcome_class = "state_stability"
            confidence = 0.88 if verified else 0.86
            reason_codes.append(
                "state_stability_observed" if verified else "state_stability_not_observed"
            )
            sources = [
                "screenshot_hash" if condition == "screen_stable" else "visual_hash"
            ]
        else:
            outcome_class = "unknown"
            confidence = 0.30
            reason_codes.append("unknown_verification_class")

        if verified:
            result = "verified"
        elif status == "FAIL":
            result = "not_verified"
        else:
            result = "inconclusive"

        semantic_goal_verified = bool(
            verified
            and (condition in semantic_conditions or condition == "window_title_contains")
        )
        state_only_verified = bool(
            verified
            and (condition in state_change_conditions or condition in stability_conditions)
        )

        return {
            "result": result,
            "outcome_class": outcome_class,
            "confidence": round(float(confidence), 2),
            "confidence_label": (
                "high" if confidence >= 0.90 else "medium" if confidence >= 0.70 else "low"
            ),
            "condition_verified": verified,
            "semantic_goal_verified": semantic_goal_verified,
            "state_only_verified": state_only_verified,
            "state_delta": state_delta,
            "evidence_sources": sources,
            "reason_codes": reason_codes,
            "evidence": evidence,
        }

    @classmethod
    def _evaluate_condition(
        cls,
        observation: dict,
        *,
        condition: str,
        target: str = "",
        prior: dict | None = None,
    ) -> tuple[str, dict]:
        condition = str(condition or "").strip().lower()
        wanted = cls._normalize(target)
        haystack = cls._element_haystack(observation)
        title = cls._normalize((observation.get("foreground") or {}).get("title", ""))

        if condition == "element_exists":
            matched = [value for value in haystack if wanted and wanted in value]
            return ("PASS" if matched else "FAIL", {"matches": matched[:8]})
        if condition == "element_absent":
            matched = [value for value in haystack if wanted and wanted in value]
            return ("PASS" if not matched else "FAIL", {"matches": matched[:8]})
        if condition == "text_contains":
            matched = [value for value in haystack if wanted and wanted in value]
            return ("PASS" if matched else "FAIL", {"matches": matched[:8]})
        if condition == "window_title_contains":
            ok = bool(wanted and wanted in title)
            return ("PASS" if ok else "FAIL", {"window_title": title})

        if condition in {
            "screen_changed",
            "screen_stable",
            "visual_changed",
            "visual_stable",
            "foreground_changed",
        }:
            if not prior:
                return ("INCONCLUSIVE", {"reason": "prior observation required"})
            if condition == "screen_changed":
                changed = (
                    observation.get("screenshot", {}).get("sha256")
                    != prior.get("screenshot", {}).get("sha256")
                )
                return ("PASS" if changed else "FAIL", {"changed": changed})
            if condition == "screen_stable":
                stable = (
                    observation.get("screenshot", {}).get("sha256")
                    == prior.get("screenshot", {}).get("sha256")
                )
                return ("PASS" if stable else "FAIL", {"stable": stable})
            if condition == "visual_changed":
                changed = cls._visual_hash(observation) != cls._visual_hash(prior)
                return (
                    "PASS" if changed else "FAIL",
                    {"visual_changed": changed},
                )
            if condition == "visual_stable":
                stable = cls._visual_hash(observation) == cls._visual_hash(prior)
                return (
                    "PASS" if stable else "FAIL",
                    {"visual_stable": stable},
                )
            changed = (
                observation.get("foreground", {}).get("hwnd")
                != prior.get("foreground", {}).get("hwnd")
            )
            return ("PASS" if changed else "FAIL", {"foreground_changed": changed})

        return ("INCONCLUSIVE", {"reason": "unsupported condition"})

    def verify(
        self,
        *,
        condition: str,
        target: str = "",
        prior_observation_id: str = "",
        vision: str = "auto",
        scope: str = "auto",
    ) -> dict:
        condition = str(condition or "").strip().lower()
        if condition not in self.VERIFY_CONDITIONS:
            raise ValueError("Unsupported computer verification condition.")

        prior = None
        if prior_observation_id:
            prior = self._observations.get(str(prior_observation_id).strip())

        observation = self.observe(vision=vision, scope=scope, max_elements=180)
        status, evidence = self._evaluate_condition(
            observation,
            condition=condition,
            target=target,
            prior=prior,
        )

        vision_escalated = False
        assessment = self._verification_assessment(
            condition=condition,
            status=status,
            evidence=evidence,
            observation=observation,
            prior=prior,
            vision_escalated=False,
        )

        verification_key = ":".join(
            (condition, self._normalize(target), str(scope or "auto").strip().lower())
        )
        current_failures = int(self._verification_failures.get(verification_key, 0))
        can_escalate_vision = bool(
            vision == "auto" and self._omniparser_endpoint()
        )

        # Let the outcome policy decide whether semantic evidence needs a visual
        # confirmation pass. This replaces ad-hoc fallback logic with the same
        # policy contract used by retry/recovery decisions.
        provisional_decision = decide_outcome(
            assessment,
            condition=condition,
            vision_escalated=False,
            can_escalate_vision=can_escalate_vision,
            failure_count=current_failures,
            max_retries=DEFAULT_MAX_RETRIES,
        )

        if provisional_decision["action"] == ESCALATE_VISION:
            observation = self.observe(
                vision="always",
                scope=scope,
                max_elements=180,
            )
            status, evidence = self._evaluate_condition(
                observation,
                condition=condition,
                target=target,
                prior=prior,
            )
            vision_escalated = True
            assessment = self._verification_assessment(
                condition=condition,
                status=status,
                evidence=evidence,
                observation=observation,
                prior=prior,
                vision_escalated=True,
            )

        if status == "PASS":
            failure_count = 0
            self._verification_failures.pop(verification_key, None)
        else:
            failure_count = current_failures + 1
            self._verification_failures[verification_key] = failure_count

        decision = decide_outcome(
            assessment,
            condition=condition,
            vision_escalated=vision_escalated,
            can_escalate_vision=False,
            failure_count=failure_count,
            max_retries=DEFAULT_MAX_RETRIES,
        )

        return {
            "status": status,
            "condition": condition,
            "target": target,
            "scope": scope,
            "evidence": evidence,
            "observation": observation,
            "prior_foreground": (
                dict(prior.get("foreground") or {}) if isinstance(prior, dict) else {}
            ),
            "vision_escalated": vision_escalated,
            "verified": status == "PASS",
            "assessment": assessment,
            "confidence": assessment["confidence"],
            "semantic_goal_verified": assessment["semantic_goal_verified"],
            "state_only_verified": assessment["state_only_verified"],
            "decision": decision,
            "recommended_action": decision["action"],
            "retry_budget_remaining": decision["retry_budget_remaining"],
        }
