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
        "foreground_changed",
    }

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

        root = Path.home() / ".iras" / "computer_use"
        root.mkdir(parents=True, exist_ok=True)
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
            label = name or automation_id or str(raw.get("role") or "UI element")
            output.append(
                {
                    "element_id": f"uia:{index}",
                    "source": "uia",
                    "label": label,
                    "name": name,
                    "automation_id": automation_id,
                    "role": str(raw.get("role") or ""),
                    "value": raw.get("value"),
                    "enabled": bool(raw.get("enabled", True)),
                    "interactive": bool(raw.get("enabled", True)),
                    "rect": normalized_rect,
                    "center": {"x": x, "y": y},
                }
            )
        return output

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
                    Path.home()
                    / ".iras"
                    / "computer_use"
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
            "uia": True,
            "omniparser_configured": bool(endpoint),
            "omniparser_endpoint": endpoint or None,
            "omniparser_available": False,
            "hybrid_mode": True,
            "coordinate_policy": "fresh_observation_element_ids_only",
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
        max_elements: int = 180,
    ) -> dict:
        self._require_windows()
        vision = str(vision or "auto").strip().lower()
        if vision not in {"off", "auto", "always"}:
            raise ValueError("vision must be off, auto, or always.")

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

        should_run_vision = (
            vision == "always"
            or (
                vision == "auto"
                and not uia_available
                and bool(self._omniparser_endpoint())
            )
        )

        vision_result = {
            "status": "not_requested" if vision == "off" else "not_needed",
            "available": False,
            "elements": [],
        }
        if should_run_vision:
            vision_result = self._run_omniparser(screenshot)
        elif vision != "off" and not self._omniparser_endpoint():
            vision_result = {
                "status": "disabled",
                "available": False,
                "elements": [],
                "reason": "IRAS_OMNIPARSER_URL is not configured.",
            }

        elements = list(uia_elements)
        elements.extend(vision_result.get("elements", []) or [])

        compact = {
            "screen_sha256": screenshot["sha256"],
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
            "uia_status": "available" if uia_available else "unavailable",
            "uia_error": uia_error or None,
            "uia_element_count": len(uia_elements),
            "vision_requested": vision,
            "vision_available": bool(vision_result.get("available")),
            "vision_status": vision_result.get("status"),
            "vision_reason": vision_result.get("reason"),
            "vision_element_count": len(vision_result.get("elements", []) or []),
            "annotated_screenshot": vision_result.get("annotated_screenshot"),
            "element_count": len(elements),
            "elements": elements,
            "action_policy": (
                "Use only element_id values from this observation. "
                "Do not invent raw click coordinates."
            ),
        }
        self._save_observation(output)
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
        previous = int((observation.get("foreground") or {}).get("hwnd", 0) or 0)
        current = int(self._foreground().get("hwnd", 0) or 0)
        return previous == current

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

        keyboard_like = action in {"type_into", "press", "hotkey", "scroll"}
        if keyboard_like and action != "type_into" and not self._foreground_still_matches(observation):
            raise RuntimeError(
                "The foreground window changed after observation. Re-observe "
                "before sending keyboard or scroll input."
            )

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
            after = self.observe(vision="auto", max_elements=180)

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
            "input_injected": True,
            "action_verified": bool(after),
            "goal_verified": False,
            "verification_observation": after,
        }

        if after:
            result["screen_changed"] = (
                observation.get("screenshot", {}).get("sha256")
                != after.get("screenshot", {}).get("sha256")
            )
            result["foreground_changed"] = (
                observation.get("foreground", {}).get("hwnd")
                != after.get("foreground", {}).get("hwnd")
            )

        return result

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
        return values

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

        if condition in {"screen_changed", "screen_stable", "foreground_changed"}:
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
    ) -> dict:
        condition = str(condition or "").strip().lower()
        if condition not in self.VERIFY_CONDITIONS:
            raise ValueError("Unsupported computer verification condition.")

        prior = None
        if prior_observation_id:
            prior = self._observations.get(str(prior_observation_id).strip())

        observation = self.observe(vision=vision, max_elements=180)
        status, evidence = self._evaluate_condition(
            observation,
            condition=condition,
            target=target,
            prior=prior,
        )

        return {
            "status": status,
            "condition": condition,
            "target": target,
            "evidence": evidence,
            "observation": observation,
            "verified": status == "PASS",
        }
