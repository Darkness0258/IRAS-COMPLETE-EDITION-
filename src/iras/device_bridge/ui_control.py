from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import time
from urllib.parse import quote

from iras.tools.system import launch_app


class WindowsUIController:
    APP_TITLES = {
        "chrome": ("Google Chrome", "Chrome"),
        "spotify": ("Spotify",),
        "code": ("Visual Studio Code",),
        "notepad": ("Notepad",),
        "explorer": ("File Explorer", "Explorer"),
    }

    APP_ALIASES = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "spotify": "spotify",
        "code": "code",
        "vscode": "code",
        "vs code": "code",
        "visual studio code": "code",
        "notepad": "notepad",
        "explorer": "explorer",
        "file explorer": "explorer",
    }

    MEDIA_KEY_CODES = {
        "next": 0xB0,
        "previous": 0xB1,
        "stop": 0xB2,
        "play_pause": 0xB3,
        "mute": 0xAD,
        "volume_down": 0xAE,
        "volume_up": 0xAF,
    }

    KEY_CODES = {
        "backspace": 0x08,
        "tab": 0x09,
        "enter": 0x0D,
        "shift": 0x10,
        "ctrl": 0x11,
        "control": 0x11,
        "alt": 0x12,
        "escape": 0x1B,
        "esc": 0x1B,
        "space": 0x20,
        "pageup": 0x21,
        "pagedown": 0x22,
        "end": 0x23,
        "home": 0x24,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
        "delete": 0x2E,
        "f2": 0x71,
        "f3": 0x72,
        "f4": 0x73,
        "f5": 0x74,
        "f6": 0x75,
        "f7": 0x76,
        "f8": 0x77,
        "f9": 0x78,
        "f10": 0x79,
        "f11": 0x7A,
        "f12": 0x7B,
    }

    ALLOWED_ACTIONS = {
        "wait",
        "type",
        "press",
        "hotkey",
        "click",
        "double_click",
        "scroll",
    }

    def __init__(self):
        self._windows = os.name == "nt"

    @classmethod
    def canonical_app(cls, app: str) -> str:
        normalized = " ".join(
            str(app or "").lower().replace("-", " ").split()
        )
        canonical = cls.APP_ALIASES.get(normalized)
        if not canonical:
            raise PermissionError(
                "Desktop interaction is limited to approved applications."
            )
        return canonical

    @classmethod
    def _key_code(cls, key: str) -> int:
        normalized = str(key or "").strip().lower()
        if len(normalized) == 1:
            char = normalized.upper()
            if "A" <= char <= "Z" or "0" <= char <= "9":
                return ord(char)

        code = cls.KEY_CODES.get(normalized)
        if code is None:
            raise PermissionError(
                f"Keyboard key '{key}' is not allowed."
            )
        return code

    @classmethod
    def validate_actions(cls, actions) -> list[dict]:
        if not isinstance(actions, list):
            raise ValueError("actions must be a list.")
        if not actions:
            raise ValueError("At least one desktop action is required.")
        if len(actions) > 15:
            raise PermissionError(
                "A desktop interaction is limited to 15 actions."
            )

        validated = []
        total_text = 0
        total_wait = 0.0

        for raw in actions:
            if not isinstance(raw, dict):
                raise ValueError(
                    "Every desktop action must be an object."
                )

            action = str(raw.get("action", "")).strip().lower()
            if action not in cls.ALLOWED_ACTIONS:
                raise PermissionError(
                    f"Desktop action '{action}' is not allowed."
                )

            item = {"action": action}

            if action == "wait":
                seconds = float(raw.get("seconds", 0.5))
                if not (0.05 <= seconds <= 4.0):
                    raise PermissionError(
                        "Each wait must be between 0.05 and 4 seconds."
                    )
                total_wait += seconds
                if total_wait > 12.0:
                    raise PermissionError(
                        "Total wait time is limited to 12 seconds."
                    )
                item["seconds"] = seconds

            elif action == "type":
                text = str(raw.get("text", ""))
                if not text:
                    raise ValueError("type action requires text.")
                if "\x00" in text:
                    raise PermissionError(
                        "NUL characters are not allowed."
                    )
                if len(text) > 1800:
                    raise PermissionError(
                        "A single type action is limited to 1800 characters."
                    )
                total_text += len(text)
                if total_text > 4000:
                    raise PermissionError(
                        "Total typed text is limited to 4000 characters."
                    )
                item["text"] = text

            elif action == "press":
                key = str(raw.get("key", "")).strip().lower()
                cls._key_code(key)
                item["key"] = key

            elif action == "hotkey":
                keys = raw.get("keys")
                if not isinstance(keys, list) or not (2 <= len(keys) <= 3):
                    raise ValueError("hotkey requires 2 or 3 keys.")
                normalized = [
                    str(key).strip().lower()
                    for key in keys
                ]

                if any(
                    key in {"win", "windows", "meta"}
                    for key in normalized
                ):
                    raise PermissionError(
                        "Windows-key shortcuts are not allowed remotely."
                    )

                key_set = set(normalized)
                if (
                    {"ctrl", "alt", "delete"}.issubset(key_set)
                    or {"control", "alt", "delete"}.issubset(key_set)
                ):
                    raise PermissionError(
                        "Ctrl+Alt+Delete is not allowed."
                    )
                if "alt" in key_set and "f4" in key_set:
                    raise PermissionError(
                        "Alt+F4 is not allowed remotely."
                    )

                for key in normalized:
                    cls._key_code(key)

                item["keys"] = normalized

            elif action in {"click", "double_click"}:
                x = int(raw.get("x", -1))
                y = int(raw.get("y", -1))
                if x < 0 or y < 0:
                    raise ValueError(
                        "click requires non-negative x and y coordinates."
                    )
                item["x"] = x
                item["y"] = y

            elif action == "scroll":
                amount = int(raw.get("amount", 0))
                if amount == 0:
                    raise ValueError(
                        "scroll requires a non-zero amount."
                    )
                if not (-10 <= amount <= 10):
                    raise PermissionError(
                        "scroll amount must be between -10 and 10."
                    )
                item["amount"] = amount

            validated.append(item)

        return validated

    def _require_windows(self):
        if not self._windows:
            raise RuntimeError(
                "Desktop interaction is only available on Windows."
            )

    def _user32(self):
        self._require_windows()
        return ctypes.windll.user32

    def _find_window(self, app: str) -> int | None:
        canonical = self.canonical_app(app)
        needles = tuple(
            item.lower() for item in self.APP_TITLES[canonical]
        )

        user32 = self._user32()
        found = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )

        @callback_type
        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True

            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True

            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.lower()

            if any(needle in title for needle in needles):
                found.append(int(hwnd))
                return False

            return True

        user32.EnumWindows(callback, 0)
        return found[0] if found else None

    def _force_foreground(
        self,
        hwnd: int,
    ) -> bool:
        user32 = self._user32()
        kernel32 = ctypes.windll.kernel32

        SW_RESTORE = 9
        VK_MENU = 0x12
        KEYEVENTF_KEYUP = 0x0002

        for _attempt in range(3):
            foreground = user32.GetForegroundWindow()

            if int(foreground or 0) == int(hwnd):
                return True

            current_thread = kernel32.GetCurrentThreadId()
            target_thread = user32.GetWindowThreadProcessId(
                hwnd,
                None,
            )
            foreground_thread = (
                user32.GetWindowThreadProcessId(
                    foreground,
                    None,
                )
                if foreground
                else 0
            )

            attached = []

            try:
                for thread_id in {
                    int(target_thread or 0),
                    int(foreground_thread or 0),
                }:
                    if (
                        thread_id
                        and thread_id != current_thread
                    ):
                        if user32.AttachThreadInput(
                            current_thread,
                            thread_id,
                            True,
                        ):
                            attached.append(thread_id)

                user32.ShowWindowAsync(
                    hwnd,
                    SW_RESTORE,
                )

                user32.keybd_event(
                    VK_MENU,
                    0,
                    0,
                    0,
                )
                user32.keybd_event(
                    VK_MENU,
                    0,
                    KEYEVENTF_KEYUP,
                    0,
                )

                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.SetActiveWindow(hwnd)
                user32.SetFocus(hwnd)

            finally:
                for thread_id in reversed(attached):
                    user32.AttachThreadInput(
                        current_thread,
                        thread_id,
                        False,
                    )

            time.sleep(0.18)

            if (
                int(user32.GetForegroundWindow() or 0)
                == int(hwnd)
            ):
                return True

        return False

    def focus_app(
        self,
        app: str,
        *,
        ensure_open: bool = True,
    ) -> dict:
        canonical = self.canonical_app(app)
        hwnd = self._find_window(canonical)
        launched = False

        if hwnd is None and ensure_open:
            launch_app(canonical)
            launched = True
            deadline = time.monotonic() + 10.0

            while time.monotonic() < deadline:
                time.sleep(0.35)
                hwnd = self._find_window(canonical)
                if hwnd is not None:
                    break

        if hwnd is None:
            raise RuntimeError(
                f"Could not find a visible {canonical} window."
            )

        if not self._force_foreground(hwnd):
            raise RuntimeError(
                f"Windows refused to focus the {canonical} window. "
                "IRAS did not send keyboard input to avoid controlling "
                "the wrong application."
            )

        return {
            "app": canonical,
            "window": hwnd,
            "launched": launched,
            "foreground_verified": True,
        }

    def _key_event(self, key: str, down: bool):
        code = self._key_code(key)
        flags = 0 if down else 0x0002
        self._user32().keybd_event(
            code,
            0,
            flags,
            0,
        )

    def press(self, key: str):
        self._key_event(key, True)
        time.sleep(0.02)
        self._key_event(key, False)

    def hotkey(self, keys: list[str]):
        for key in keys:
            self._key_event(key, True)
            time.sleep(0.015)

        for key in reversed(keys):
            self._key_event(key, False)
            time.sleep(0.015)

    def _set_clipboard_text(self, text: str):
        self._require_windows()

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        encoded = (str(text) + "\x00").encode("utf-16-le")
        handle = kernel32.GlobalAlloc(
            GMEM_MOVEABLE,
            len(encoded),
        )
        if not handle:
            raise RuntimeError(
                "Could not allocate clipboard memory."
            )

        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            raise RuntimeError(
                "Could not lock clipboard memory."
            )

        try:
            ctypes.memmove(pointer, encoded, len(encoded))
        finally:
            kernel32.GlobalUnlock(handle)

        deadline = time.monotonic() + 2.0
        while not user32.OpenClipboard(None):
            if time.monotonic() >= deadline:
                kernel32.GlobalFree(handle)
                raise RuntimeError(
                    "Could not open Windows clipboard."
                )
            time.sleep(0.05)

        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(
                CF_UNICODETEXT,
                handle,
            ):
                kernel32.GlobalFree(handle)
                raise RuntimeError(
                    "Could not set clipboard data."
                )
            handle = None
        finally:
            user32.CloseClipboard()

        if handle:
            kernel32.GlobalFree(handle)

    def type_text(self, text: str):
        self._require_windows()

        value = str(text)

        if not value:
            return

        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_UNICODE = 0x0004

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.WPARAM),
            ]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.WPARAM),
            ]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [
                ("uMsg", wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD),
            ]

        class INPUTUNION(ctypes.Union):
            _fields_ = [
                ("mi", MOUSEINPUT),
                ("ki", KEYBDINPUT),
                ("hi", HARDWAREINPUT),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [
                ("type", wintypes.DWORD),
                ("u", INPUTUNION),
            ]

        utf16 = value.encode("utf-16-le")

        code_units = [
            int.from_bytes(
                utf16[index:index + 2],
                "little",
            )
            for index in range(
                0,
                len(utf16),
                2,
            )
        ]

        events = []

        for code_unit in code_units:
            key_down = INPUT()
            key_down.type = INPUT_KEYBOARD
            key_down.u.ki = KEYBDINPUT(
                0,
                code_unit,
                KEYEVENTF_UNICODE,
                0,
                0,
            )

            key_up = INPUT()
            key_up.type = INPUT_KEYBOARD
            key_up.u.ki = KEYBDINPUT(
                0,
                code_unit,
                KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                0,
                0,
            )

            events.extend([key_down, key_up])

        array_type = INPUT * len(events)
        array = array_type(*events)

        sent = self._user32().SendInput(
            len(events),
            array,
            ctypes.sizeof(INPUT),
        )

        if sent != len(events):
            raise RuntimeError(
                "Windows could not inject all requested text input."
            )

        time.sleep(
            min(
                0.35,
                0.01 + (len(code_units) * 0.001),
            )
        )

    def click(
        self,
        x: int,
        y: int,
        *,
        double: bool = False,
    ):
        user32 = self._user32()
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)

        if not (
            0 <= x < width
            and 0 <= y < height
        ):
            raise ValueError(
                "Click coordinates are outside the primary display."
            )

        user32.SetCursorPos(x, y)
        clicks = 2 if double else 1

        for _ in range(clicks):
            user32.mouse_event(
                0x0002,
                0,
                0,
                0,
                0,
            )
            user32.mouse_event(
                0x0004,
                0,
                0,
                0,
                0,
            )
            if double:
                time.sleep(0.08)

    def scroll(self, amount: int):
        self._user32().mouse_event(
            0x0800,
            0,
            0,
            ctypes.c_ulong(
                int(amount) * 120
            ).value,
            0,
        )

    def _open_spotify_search_uri(
        self,
        query: str,
    ) -> bool:
        self._require_windows()

        uri = (
            "spotify:search:"
            + quote(query, safe="")
        )

        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "open",
            uri,
            None,
            None,
            1,
        )

        return int(result) > 32

    def _physical_window_rect(
        self,
        hwnd: int,
    ):
        # Return physical-pixel window bounds so ImageGrab and mouse
        # coordinates use the same DPI coordinate system.
        self._require_windows()

        rect = wintypes.RECT()

        try:
            DWMWA_EXTENDED_FRAME_BOUNDS = 9

            result = (
                ctypes.windll.dwmapi
                .DwmGetWindowAttribute(
                    hwnd,
                    DWMWA_EXTENDED_FRAME_BOUNDS,
                    ctypes.byref(rect),
                    ctypes.sizeof(rect),
                )
            )

            if result == 0:
                return rect

        except Exception:
            pass

        if not self._user32().GetWindowRect(
            hwnd,
            ctypes.byref(rect),
        ):
            raise RuntimeError(
                "Could not read the Spotify window position."
            )

        return rect

    def _set_physical_cursor(
        self,
        x: int,
        y: int,
    ) -> dict:
        # Move and verify the cursor in physical screen pixels.
        user32 = self._user32()

        moved = False

        try:
            moved = bool(
                user32.SetPhysicalCursorPos(
                    int(x),
                    int(y),
                )
            )
        except Exception:
            moved = bool(
                user32.SetCursorPos(
                    int(x),
                    int(y),
                )
            )

        if not moved:
            raise RuntimeError(
                "Windows refused to move the cursor to the Spotify Play button."
            )

        point = wintypes.POINT()

        try:
            ok = user32.GetPhysicalCursorPos(
                ctypes.byref(point)
            )
        except Exception:
            ok = user32.GetCursorPos(
                ctypes.byref(point)
            )

        if not ok:
            raise RuntimeError(
                "Could not verify the physical cursor position."
            )

        actual_x = int(point.x)
        actual_y = int(point.y)

        if (
            abs(actual_x - int(x)) > 3
            or abs(actual_y - int(y)) > 3
        ):
            raise RuntimeError(
                "Windows DPI scaling moved the cursor away from the requested "
                f"Spotify button position: requested=({x},{y}) "
                f"actual=({actual_x},{actual_y})."
            )

        return {
            "requested_x": int(x),
            "requested_y": int(y),
            "actual_x": actual_x,
            "actual_y": actual_y,
        }

    def _send_spotify_play_command(
        self,
        hwnd: int,
    ) -> bool:
        # Explicit PLAY, not PLAY_PAUSE, so this is idempotent.
        user32 = self._user32()

        WM_APPCOMMAND = 0x0319
        APPCOMMAND_MEDIA_PLAY = 46
        SMTO_ABORTIFHUNG = 0x0002

        result_value = ctypes.c_size_t()

        try:
            sent = user32.SendMessageTimeoutW(
                hwnd,
                WM_APPCOMMAND,
                hwnd,
                APPCOMMAND_MEDIA_PLAY << 16,
                SMTO_ABORTIFHUNG,
                1500,
                ctypes.byref(result_value),
            )
        except Exception:
            return False

        return bool(sent)

    @staticmethod
    def _spotify_green_components(
        image,
    ) -> list[dict]:
        image = image.convert("RGB")
        pixels = image.load()
        width, height = image.size

        mask = bytearray(
            width * height
        )

        for y in range(height):
            row = y * width

            for x in range(width):
                r, g, b = pixels[
                    x,
                    y,
                ]

                if (
                    g >= 145
                    and g >= r + 65
                    and g >= b + 40
                    and r <= 125
                    and b <= 180
                ):
                    mask[
                        row + x
                    ] = 1

        visited = bytearray(
            width * height
        )
        components = []

        for y in range(height):
            for x in range(width):
                index = (
                    y * width
                    + x
                )

                if (
                    not mask[index]
                    or visited[index]
                ):
                    continue

                stack = [
                    index
                ]
                visited[
                    index
                ] = 1

                count = 0
                sum_x = 0
                sum_y = 0
                min_x = x
                max_x = x
                min_y = y
                max_y = y

                while stack:
                    current = stack.pop()
                    cy, cx = divmod(
                        current,
                        width,
                    )

                    count += 1
                    sum_x += cx
                    sum_y += cy

                    min_x = min(
                        min_x,
                        cx,
                    )
                    max_x = max(
                        max_x,
                        cx,
                    )
                    min_y = min(
                        min_y,
                        cy,
                    )
                    max_y = max(
                        max_y,
                        cy,
                    )

                    neighbors = []

                    if cx > 0:
                        neighbors.append(
                            current - 1
                        )

                    if (
                        cx + 1
                        < width
                    ):
                        neighbors.append(
                            current + 1
                        )

                    if cy > 0:
                        neighbors.append(
                            current - width
                        )

                    if (
                        cy + 1
                        < height
                    ):
                        neighbors.append(
                            current + width
                        )

                    for neighbor in neighbors:
                        if (
                            mask[neighbor]
                            and not visited[
                                neighbor
                            ]
                        ):
                            visited[
                                neighbor
                            ] = 1
                            stack.append(
                                neighbor
                            )

                components.append(
                    {
                        "green_pixels": count,
                        "x": int(
                            sum_x / count
                        ),
                        "y": int(
                            sum_y / count
                        ),
                        "width": (
                            max_x
                            - min_x
                            + 1
                        ),
                        "height": (
                            max_y
                            - min_y
                            + 1
                        ),
                    }
                )

        return components

    def _spotify_play_button_point(
        self,
        hwnd: int,
    ):
        self._require_windows()

        from PIL import ImageGrab

        rect = self._physical_window_rect(
            hwnd
        )

        left = int(rect.left)
        top = int(rect.top)
        right = int(rect.right)
        bottom = int(rect.bottom)

        width = max(
            1,
            right - left,
        )
        height = max(
            1,
            bottom - top,
        )

        roi_left = int(
            width * 0.20
        )
        roi_right = int(
            width * 0.82
        )
        roi_top = int(
            height * 0.07
        )
        roi_bottom = int(
            height * 0.42
        )

        bbox = (
            left + roi_left,
            top + roi_top,
            left + roi_right,
            top + roi_bottom,
        )

        try:
            image = ImageGrab.grab(
                bbox=bbox,
                all_screens=True,
            ).convert("RGB")
        except TypeError:
            image = ImageGrab.grab(
                bbox=bbox,
            ).convert("RGB")

        candidates = []

        for component in (
            self._spotify_green_components(
                image
            )
        ):
            if (
                component[
                    "green_pixels"
                ]
                >= 350
                and 24
                <= component[
                    "width"
                ]
                <= 110
                and 24
                <= component[
                    "height"
                ]
                <= 110
            ):
                candidates.append(
                    component
                )

        if not candidates:
            return None

        best = max(
            candidates,
            key=lambda item: (
                item[
                    "green_pixels"
                ],
                item[
                    "width"
                ]
                * item[
                    "height"
                ],
            ),
        )

        return {
            "x": (
                left
                + roi_left
                + best["x"]
            ),
            "y": (
                top
                + roi_top
                + best["y"]
            ),
            "green_pixels": (
                best[
                    "green_pixels"
                ]
            ),
            "component_width": (
                best[
                    "width"
                ]
            ),
            "component_height": (
                best[
                    "height"
                ]
            ),
        }

    def _wait_for_spotify_play_button(
        self,
        hwnd: int,
        *,
        timeout: float = 8.0,
    ):
        deadline = (
            time.monotonic()
            + max(
                1.0,
                float(timeout),
            )
        )

        attempts = 0

        while (
            time.monotonic()
            < deadline
        ):
            attempts += 1

            point = (
                self._spotify_play_button_point(
                    hwnd
                )
            )

            if point is not None:
                point[
                    "detection_attempts"
                ] = attempts

                return point

            time.sleep(
                0.30
            )

        return None

    def _click_spotify_play_button(
        self,
        hwnd: int,
    ) -> dict:
        # Never guess a coordinate. A guessed click plus MEDIA_PLAY can
        # resume the previous track instead of starting the requested result.
        point = (
            self._wait_for_spotify_play_button(
                hwnd,
                timeout=8.0,
            )
        )

        if point is None:
            raise RuntimeError(
                "IRAS could not detect Spotify's green Top Result Play button "
                "within 8 seconds. No fallback click or generic MEDIA_PLAY "
                "command was sent, so the previous track was not resumed."
            )

        if not self._force_foreground(
            hwnd
        ):
            raise RuntimeError(
                "Spotify lost foreground focus before IRAS could press Play."
            )

        cursor = self._set_physical_cursor(
            int(point["x"]),
            int(point["y"]),
        )

        time.sleep(
            0.12
        )

        user32 = self._user32()

        user32.mouse_event(
            0x0002,
            0,
            0,
            0,
            0,
        )
        time.sleep(
            0.045
        )
        user32.mouse_event(
            0x0004,
            0,
            0,
            0,
            0,
        )

        time.sleep(
            0.70
        )

        return {
            "detected": True,
            "media_play_sent": False,
            "cursor_actual_x": cursor[
                "actual_x"
            ],
            "cursor_actual_y": cursor[
                "actual_y"
            ],
            **point,
        }

    def spotify_search(
        self,
        query: str,
    ) -> dict:
        query = " ".join(
            str(query or "")
            .strip()
            .split()
        )

        if not query:
            raise ValueError(
                "Spotify search requires a query."
            )

        if len(query) > 220:
            raise PermissionError(
                "Spotify query is too long."
            )

        deep_link_opened = False

        try:
            deep_link_opened = (
                self._open_spotify_search_uri(
                    query
                )
            )
        except Exception:
            deep_link_opened = False

        if deep_link_opened:
            time.sleep(1.0)

        focused = self.focus_app(
            "spotify",
            ensure_open=True,
        )

        if not deep_link_opened:
            self.hotkey(
                [
                    "ctrl",
                    "k",
                ]
            )
            time.sleep(0.25)
            self.hotkey(
                [
                    "ctrl",
                    "a",
                ]
            )
            time.sleep(0.05)
            self.type_text(
                query
            )
            time.sleep(0.45)

        print(
            "[IRAS SPOTIFY SEARCH] "
            f"query={query!r} "
            f"deep_link={deep_link_opened} "
            f"foreground={focused.get('foreground_verified', False)}",
            flush=True,
        )

        return {
            "app": "spotify",
            "query": query,
            "deep_link_opened": deep_link_opened,
            "foreground_verified": focused.get(
                "foreground_verified",
                False,
            ),
            "search_opened": True,
        }

    def _play_spotify_quick_search_result(
        self,
        hwnd: int,
    ) -> dict:
        if not self._force_foreground(int(hwnd)):
            raise RuntimeError(
                "Spotify lost foreground focus before IRAS could play "
                "the highlighted search result."
            )

        self.hotkey(
            [
                "shift",
                "enter",
            ]
        )
        time.sleep(1.0)

        return {
            "shortcut": "shift+enter",
            "foreground_verified": True,
            "requested_action": "play_highlighted_search_result",
        }

    def spotify_play(
        self,
        query: str,
    ) -> dict:
        query = " ".join(
            str(query or "").strip().split()
        )

        if not query:
            raise ValueError(
                "Spotify play requires a song or search query."
            )

        if len(query) > 220:
            raise PermissionError(
                "Spotify query is too long."
            )

        deep_link_opened = False
        try:
            deep_link_opened = self._open_spotify_search_uri(query)
        except Exception:
            deep_link_opened = False

        if deep_link_opened:
            time.sleep(1.25)

        focused = self.focus_app(
            "spotify",
            ensure_open=True,
        )

        self.hotkey(["ctrl", "k"])
        time.sleep(0.30)
        self.hotkey(["ctrl", "a"])
        time.sleep(0.06)
        self.type_text(query)
        time.sleep(1.05)

        play_method = "quick_search_shift_enter"
        quick_search_play = None
        play_click = None
        quick_search_error = ""

        try:
            quick_search_play = self._play_spotify_quick_search_result(
                int(focused["window"])
            )
        except Exception as exc:
            # Legacy compatibility only. Never send generic MEDIA_PLAY here.
            quick_search_error = str(exc)
            self.press("enter")
            time.sleep(1.05)
            play_click = self._click_spotify_play_button(
                int(focused["window"])
            )
            play_method = "legacy_green_play_button"

        if quick_search_play is not None:
            print(
                "[IRAS SPOTIFY] "
                f"query={query!r} deep_link={deep_link_opened} "
                f"foreground={focused.get('foreground_verified', False)} "
                "method=quick_search_shift_enter shortcut=shift+enter",
                flush=True,
            )
        else:
            print(
                "[IRAS SPOTIFY] "
                f"query={query!r} deep_link={deep_link_opened} "
                f"foreground={focused.get('foreground_verified', False)} "
                "method=legacy_green_play_button "
                f"quick_search_error={quick_search_error!r} "
                f"play_click=({play_click['x']},{play_click['y']}) "
                f"green_detected={play_click['detected']} "
                f"green_pixels={play_click['green_pixels']} "
                f"green_size=({play_click['component_width']}x"
                f"{play_click['component_height']}) "
                f"attempts={play_click['detection_attempts']} "
                f"cursor_actual=({play_click['cursor_actual_x']},"
                f"{play_click['cursor_actual_y']})",
                flush=True,
            )

        return {
            "app": "spotify",
            "query": query,
            "launched": focused["launched"],
            "deep_link_opened": deep_link_opened,
            "foreground_verified": focused.get(
                "foreground_verified",
                False,
            ),
            "search_input_sent": True,
            "playback_method": play_method,
            "quick_search_play_sent": quick_search_play is not None,
            "quick_search_shortcut": (
                "shift+enter" if quick_search_play is not None else None
            ),
            "play_button_clicked": play_click is not None,
            "play_button_detected": bool(
                play_click and play_click.get("detected")
            ),
            "play_click": (
                {
                    "x": play_click["x"],
                    "y": play_click["y"],
                    "actual_x": play_click["cursor_actual_x"],
                    "actual_y": play_click["cursor_actual_y"],
                }
                if play_click else None
            ),
            "media_play_sent": False,
            "play_button_detection_attempts": (
                play_click["detection_attempts"] if play_click else 0
            ),
            "command_sent": True,
            "verified_playback": False,
            "note": (
                "Spotify Quick Search was focused, the requested query was "
                "typed, and IRAS sent Spotify's own Shift+Enter Play shortcut "
                "for the highlighted result. No generic MEDIA_PLAY command "
                "was sent."
                if quick_search_play is not None
                else
                "Spotify Quick Search playback could not be injected, so "
                "IRAS used the existing detected green Play-button fallback. "
                "No generic MEDIA_PLAY command was sent."
            ),
        }

    def _send_media_appcommand(
        self,
        command_id: int,
        *,
        hwnd: int | None = None,
    ) -> bool:
        self._require_windows()

        user32 = self._user32()

        if hwnd is None:
            hwnd = self._find_window(
                "spotify"
            )

        if hwnd is None:
            hwnd = int(
                user32.GetForegroundWindow()
                or 0
            )

        if not hwnd:
            return False

        WM_APPCOMMAND = 0x0319
        SMTO_ABORTIFHUNG = 0x0002

        result_value = ctypes.c_size_t()

        try:
            sent = user32.SendMessageTimeoutW(
                hwnd,
                WM_APPCOMMAND,
                hwnd,
                int(command_id) << 16,
                SMTO_ABORTIFHUNG,
                1500,
                ctypes.byref(result_value),
            )
        except Exception:
            return False

        return bool(sent)

    def media_control(
        self,
        command: str,
    ) -> dict:
        normalized = " ".join(
            str(command or "")
            .lower()
            .replace("-", "_")
            .split()
        )

        aliases = {
            "resume": "play",
            "play pause": "play_pause",
            "next song": "next",
            "next track": "next",
            "previous song": "previous",
            "previous track": "previous",
            "volume up": "volume_up",
            "volume down": "volume_down",
            "shuffle": "shuffle_toggle",
            "repeat": "repeat_toggle",
            "like": "like_toggle",
            "queue": "open_queue",
            "liked songs": "open_liked_songs",
            "now playing": "open_now_playing",
        }

        action = aliases.get(
            normalized,
            normalized,
        )

        app_commands = {
            "next": 11,
            "previous": 12,
            "stop": 13,
            "play_pause": 14,
            "mute": 8,
            "unmute": 8,
            "volume_down": 9,
            "volume_up": 10,
            "play": 46,
            "pause": 47,
        }

        if action in app_commands:
            sent = self._send_media_appcommand(
                app_commands[
                    action
                ]
            )

            if not sent:
                raise RuntimeError(
                    f"Windows rejected the {action} media command."
                )

            return {
                "command": action,
                "command_sent": True,
                "transport": "wm_appcommand",
                "verified_state": False,
            }

        spotify_shortcuts = {
            "shuffle_toggle": [
                "ctrl",
                "s",
            ],
            "repeat_toggle": [
                "ctrl",
                "r",
            ],
            "like_toggle": [
                "alt",
                "shift",
                "b",
            ],
            "open_queue": [
                "alt",
                "shift",
                "q",
            ],
            "open_liked_songs": [
                "alt",
                "shift",
                "s",
            ],
            "open_now_playing": [
                "alt",
                "shift",
                "j",
            ],
        }

        keys = spotify_shortcuts.get(
            action
        )

        if keys is None:
            raise PermissionError(
                f"Media command '{command}' is not allowed."
            )

        focused = self.focus_app(
            "spotify",
            ensure_open=True,
        )

        self.hotkey(
            keys
        )

        return {
            "command": action,
            "command_sent": True,
            "transport": "spotify_keyboard_shortcut",
            "foreground_verified": focused.get(
                "foreground_verified",
                False,
            ),
            "verified_state": False,
        }

    def interact(
        self,
        app: str,
        actions,
        *,
        ensure_open: bool = True,
    ) -> dict:
        validated = self.validate_actions(actions)
        focused = self.focus_app(
            app,
            ensure_open=ensure_open,
        )

        completed = []

        for action in validated:
            kind = action["action"]

            if kind == "wait":
                time.sleep(action["seconds"])
            elif kind == "type":
                self.type_text(action["text"])
            elif kind == "press":
                self.press(action["key"])
            elif kind == "hotkey":
                self.hotkey(action["keys"])
            elif kind == "click":
                self.click(
                    action["x"],
                    action["y"],
                )
            elif kind == "double_click":
                self.click(
                    action["x"],
                    action["y"],
                    double=True,
                )
            elif kind == "scroll":
                self.scroll(action["amount"])

            completed.append(kind)
            time.sleep(0.08)

        return {
            "app": focused["app"],
            "launched": focused["launched"],
            "actions_completed": completed,
        }
