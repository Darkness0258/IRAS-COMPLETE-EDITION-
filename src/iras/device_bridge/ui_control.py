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

    def _window_visual_signature(self, hwnd: int):
        """Return a tiny visual fingerprint for readiness/stability checks.

        This is deliberately read-only.  It lets the Spotify fast path wait
        for the real application window to finish opening/rendering instead
        of relying on a single fixed sleep and then typing into a half-loaded
        UI.  Failure to capture is tolerated by the caller, which falls back
        to foreground + elapsed-time readiness.
        """
        self._require_windows()
        from PIL import ImageGrab

        rect = self._physical_window_rect(hwnd)
        left = int(rect.left)
        top = int(rect.top)
        right = int(rect.right)
        bottom = int(rect.bottom)
        width = max(1, right - left)
        height = max(1, bottom - top)
        if width < 320 or height < 240:
            return None

        # Ignore most window chrome/taskbar edges and fingerprint the content.
        bbox = (
            left + int(width * 0.08),
            top + int(height * 0.10),
            right - int(width * 0.05),
            bottom - int(height * 0.06),
        )
        try:
            image = ImageGrab.grab(bbox=bbox, all_screens=True)
        except TypeError:
            image = ImageGrab.grab(bbox=bbox)
        image = image.convert("L").resize((32, 18))
        return tuple(image.getdata())

    @staticmethod
    def _visual_signature_delta(left, right) -> float:
        if not left or not right or len(left) != len(right):
            return 999.0
        return sum(abs(int(a) - int(b)) for a, b in zip(left, right)) / len(left)

    def _wait_for_spotify_ui_ready(
        self,
        hwnd: int,
        *,
        minimum_wait: float = 0.8,
        timeout: float = 12.0,
        baseline=None,
        require_visual_change: bool = False,
        phase: str = "startup",
    ) -> dict:
        """Wait for Spotify to be visible, foreground and visually settled.

        A bounded visual-stability probe is much more reliable than firing the
        next keyboard shortcut immediately after the first window handle
        appears.  It also stays fail-closed: IRAS will not type while another
        application owns the foreground.
        """
        started = time.monotonic()
        deadline = started + max(float(timeout), float(minimum_wait), 0.5)
        previous = None
        stable_samples = 0
        visual_changed = baseline is None or not require_visual_change
        captured = False

        while time.monotonic() < deadline:
            if not self._force_foreground(int(hwnd)):
                time.sleep(0.20)
                continue

            sig = None
            try:
                sig = self._window_visual_signature(int(hwnd))
            except Exception:
                sig = None

            if sig is not None:
                captured = True
                if baseline is not None and self._visual_signature_delta(sig, baseline) >= 3.0:
                    visual_changed = True
                if previous is not None and self._visual_signature_delta(sig, previous) <= 2.0:
                    stable_samples += 1
                else:
                    stable_samples = 0
                previous = sig

            elapsed = time.monotonic() - started
            # If screen capture is unavailable, still enforce a real settle
            # window plus verified foreground instead of a zero-delay action.
            visually_ready = (captured and stable_samples >= 2 and visual_changed)
            timed_fallback_ready = (not captured and elapsed >= max(1.25, minimum_wait))
            if elapsed >= minimum_wait and (visually_ready or timed_fallback_ready):
                waited_ms = int(elapsed * 1000)
                print(
                    f"[IRAS SPOTIFY READY] phase={phase} waited={waited_ms}ms "
                    f"visual={captured} changed={visual_changed} stable={stable_samples}",
                    flush=True,
                )
                return {
                    "ready": True,
                    "waited_ms": waited_ms,
                    "visual_probe": captured,
                    "visual_changed": bool(visual_changed),
                    "stable_samples": stable_samples,
                }
            time.sleep(0.22)

        elapsed = time.monotonic() - started
        if not self._force_foreground(int(hwnd)):
            raise RuntimeError(
                "Spotify did not become the verified foreground window before the readiness timeout."
            )
        waited_ms = int(elapsed * 1000)
        print(
            f"[IRAS SPOTIFY READY] phase={phase} waited={waited_ms}ms "
            f"visual={captured} changed={visual_changed} stable={stable_samples} timeout=True",
            flush=True,
        )
        return {
            "ready": True,
            "waited_ms": waited_ms,
            "visual_probe": captured,
            "visual_changed": bool(visual_changed),
            "stable_samples": stable_samples,
            "timed_out_waiting_for_stability": True,
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

        # Deterministic sequence: open/focus first, wait for the actual Spotify
        # window to finish rendering, then interact with search.  The URI path
        # is now fallback-only instead of racing application startup.
        focused = self.focus_app(
            "spotify",
            ensure_open=True,
        )
        startup_ready = self._wait_for_spotify_ui_ready(
            int(focused["window"]),
            minimum_wait=(1.35 if focused.get("launched") else 0.35),
            timeout=(15.0 if focused.get("launched") else 6.0),
            phase="startup",
        )

        deep_link_opened = False
        search_ready = {}
        baseline = None
        try:
            baseline = self._window_visual_signature(int(focused["window"]))
        except Exception:
            baseline = None

        try:
            self.hotkey(["ctrl", "k"])
            time.sleep(0.20)
            self.hotkey(["ctrl", "a"])
            time.sleep(0.05)
            self.type_text(query)
            search_ready = self._wait_for_spotify_ui_ready(
                int(focused["window"]),
                minimum_wait=0.80,
                timeout=5.0,
                baseline=baseline,
                require_visual_change=(baseline is not None),
                phase="search_results",
            )
        except Exception:
            # URI search remains a compatibility fallback, but only after the
            # Spotify app itself has been opened and verified ready.
            deep_link_opened = self._open_spotify_search_uri(query)
            if not deep_link_opened:
                raise
            focused = self.focus_app("spotify", ensure_open=True)
            search_ready = self._wait_for_spotify_ui_ready(
                int(focused["window"]),
                minimum_wait=1.10,
                timeout=7.0,
                phase="uri_search_results",
            )

        print(
            "[IRAS SPOTIFY SEARCH] "
            f"query={query!r} "
            f"launched={focused.get('launched', False)} "
            f"deep_link={deep_link_opened} "
            f"startup_wait_ms={startup_ready.get('waited_ms')} "
            f"search_wait_ms={search_ready.get('waited_ms')} "
            f"foreground={focused.get('foreground_verified', False)}",
            flush=True,
        )

        return {
            "app": "spotify",
            "query": query,
            "launched": bool(focused.get("launched")),
            "deep_link_opened": deep_link_opened,
            "foreground_verified": focused.get(
                "foreground_verified",
                False,
            ),
            "startup_ready": startup_ready,
            "search_ready": search_ready,
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

    def _verify_spotify_playback(
        self,
        hwnd: int,
        query: str,
    ) -> dict:
        """Read back Spotify state without mistaking unrelated playback for success.

        A request such as ``play naat`` is only verified when Spotify exposes a
        playing transport *and* query-related evidence in the now-playing
        surface (right details panel or bottom transport metadata). Library or
        search-page text does not count because it can remain visible while an
        unrelated track continues playing.
        """
        try:
            from iras.device_bridge.visual_control import SemanticVisualController

            snapshot = SemanticVisualController(self).observe(
                "spotify",
                ensure_open=False,
                max_elements=320,
                screenshot=False,
            )
        except Exception as exc:
            return {
                "verified": False,
                "playing": False,
                "query_match": False,
                "spotify_error": None,
                "error": f"{type(exc).__name__}: {exc}",
                "query_evidence": [],
                "now_playing_candidates": [],
            }

        def norm(value: str) -> str:
            return " ".join(
                str(value or "")
                .strip()
                .lower()
                .replace("_", " ")
                .replace("-", " ")
                .replace("’", "'")
                .split()
            )

        elements = [
            item for item in (snapshot.get("elements") or [])
            if str(item.get("name") or "").strip()
        ]
        names = [str(item.get("name") or "").strip() for item in elements]
        normalized_names = [norm(name) for name in names]

        # Spotify's central transport changes from Play to Pause while audio is
        # actually active. A connected-device banner alone is not playback.
        playing = any(
            name == "pause" or name.startswith("pause ") or "pause current" in name
            for name in normalized_names
        )

        error_messages = []
        for original, normalized in zip(names, normalized_names):
            if (
                "spotify can't play this right now" in normalized
                or "spotify can t play this right now" in normalized
                or "can't play this right now" in normalized
                or "can t play this right now" in normalized
                or "cannot play this right now" in normalized
                or "if you have the file on your computer" in normalized
            ):
                error_messages.append(original)
        spotify_error = error_messages[0] if error_messages else None

        stop = {
            "play", "spotify", "song", "songs", "music", "track",
            "please", "some", "the", "a", "an", "on", "put", "listen",
        }
        query_terms = [
            token for token in norm(query).split()
            if len(token) >= 3 and token not in stop
        ]

        query_evidence = []
        now_candidates = []
        try:
            rect = self._physical_window_rect(int(hwnd))
            width = max(1, int(rect.right - rect.left))
            height = max(1, int(rect.bottom - rect.top))
            right_threshold = int(rect.left + width * 0.76)
            bottom_threshold = int(rect.top + height * 0.78)
            ignored = {
                "pause", "play", "next", "previous", "shuffle",
                "repeat", "queue", "mute", "lyrics", "now playing view",
            }
            for item in elements:
                item_rect = item.get("rect") or {}
                left = int(item_rect.get("left", 0) or 0)
                top = int(item_rect.get("top", 0) or 0)
                item_width = int(item_rect.get("width", 0) or 0)
                name = str(item.get("name") or "").strip()
                normalized = norm(name)
                if not name or normalized in ignored:
                    continue
                cx = left + max(0, item_width) / 2
                in_now_playing_surface = cx >= right_threshold or top >= bottom_threshold
                if not in_now_playing_surface:
                    continue
                if any(fragment in normalized for fragment in ("volume", "connect to", "full screen")):
                    continue
                if name not in now_candidates:
                    now_candidates.append(name)
                if query_terms and any(term in normalized for term in query_terms):
                    if name not in query_evidence:
                        query_evidence.append(name)
        except Exception:
            pass

        query_match = bool(query_evidence) if query_terms else True
        verified = bool(playing and query_match and not spotify_error)

        return {
            "verified": verified,
            "playing": bool(playing),
            "query_match": bool(query_match),
            "spotify_error": spotify_error,
            "error": None,
            "query_evidence": query_evidence[:8],
            "now_playing_candidates": now_candidates[:12],
            "element_count": int(snapshot.get("element_count", 0) or 0),
        }

    @staticmethod
    def _spotify_norm(value: str) -> str:
        return " ".join(
            str(value or "")
            .strip()
            .lower()
            .replace("_", " ")
            .replace("-", " ")
            .split()
        )

    @classmethod
    def _spotify_query_terms(cls, query: str) -> list[str]:
        stop = {
            "play", "spotify", "song", "songs", "music", "track",
            "please", "some", "the", "a", "an", "on", "put", "listen",
        }
        return [
            token for token in cls._spotify_norm(query).split()
            if len(token) >= 3 and token not in stop
        ]

    def _spotify_semantic_snapshot(self, hwnd: int, *, max_elements: int = 300) -> dict:
        from iras.device_bridge.visual_control import SemanticVisualController

        if not self._force_foreground(int(hwnd)):
            raise RuntimeError("Spotify lost foreground focus before semantic inspection.")
        return SemanticVisualController(self).observe(
            "spotify",
            ensure_open=False,
            max_elements=max_elements,
            screenshot=False,
        )

    def _click_spotify_observed_element(
        self,
        hwnd: int,
        element: dict,
        *,
        count: int = 1,
    ) -> dict:
        """Click only bounds returned by Windows UI Automation."""
        if not self._force_foreground(int(hwnd)):
            raise RuntimeError("Spotify lost foreground focus before semantic click.")
        rect = element.get("rect") or {}
        left = int(rect.get("left", 0) or 0)
        top = int(rect.get("top", 0) or 0)
        width = int(rect.get("width", 0) or 0)
        height = int(rect.get("height", 0) or 0)
        if width <= 0 or height <= 0:
            raise RuntimeError("Spotify semantic element has no clickable bounds.")

        win = self._physical_window_rect(int(hwnd))
        x = left + width // 2
        y = top + height // 2
        if not (int(win.left) <= x <= int(win.right) and int(win.top) <= y <= int(win.bottom)):
            raise RuntimeError("Spotify semantic element lies outside the verified window.")

        cursor = self._set_physical_cursor(x, y)
        user32 = self._user32()
        for index in range(max(1, min(int(count), 2))):
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.035)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
            if index == 0 and count > 1:
                time.sleep(0.10)
        return {
            "name": str(element.get("name") or ""),
            "role": str(element.get("role") or ""),
            "x": x,
            "y": y,
            "actual_x": cursor.get("actual_x"),
            "actual_y": cursor.get("actual_y"),
            "count": max(1, min(int(count), 2)),
            "match_score": element.get("match_score"),
        }

    def _invoke_spotify_observed_element(self, hwnd: int, element: dict) -> dict:
        """Invoke the exact observed Spotify element through the audited UIA layer."""
        if not self._force_foreground(int(hwnd)):
            raise RuntimeError("Spotify lost foreground focus before UI Automation invoke.")
        from iras.device_bridge.visual_control import SemanticVisualController
        return SemanticVisualController(self).invoke_observed_element(
            "spotify",
            element,
            ensure_open=False,
        )

    def _spotify_quick_search_overlay_present(self, hwnd: int) -> bool:
        try:
            snapshot = self._spotify_semantic_snapshot(int(hwnd), max_elements=220)
        except Exception:
            return False
        for item in snapshot.get("elements") or []:
            name = self._spotify_norm(item.get("name") or "")
            role = self._spotify_norm(item.get("role") or "")
            if "what do you want to play" in name and role in {"edit", "text", "document"}:
                return True
        return False

    def _dismiss_spotify_quick_search_overlay(self, hwnd: int) -> dict:
        """Close Spotify Quick Search if it remained open after result selection."""
        before = self._spotify_quick_search_overlay_present(int(hwnd))
        if not before:
            return {"present_before": False, "dismissed": True, "attempts": 0}

        attempts = 0
        for _ in range(2):
            attempts += 1
            if not self._force_foreground(int(hwnd)):
                raise RuntimeError("Spotify lost foreground focus while closing Quick Search.")
            self.press("esc")
            time.sleep(0.45)
            if not self._spotify_quick_search_overlay_present(int(hwnd)):
                print(
                    f"[IRAS SPOTIFY READY] phase=quick_search_dismissed attempts={attempts}",
                    flush=True,
                )
                return {"present_before": True, "dismissed": True, "attempts": attempts}

        return {"present_before": True, "dismissed": False, "attempts": attempts}

    def _spotify_find_query_results(
        self,
        hwnd: int,
        query: str,
        *,
        limit: int = 4,
    ) -> list[dict]:
        """Return ranked visible results related to the requested query."""
        snapshot = self._spotify_semantic_snapshot(hwnd)
        terms = self._spotify_query_terms(query)
        phrase = self._spotify_norm(query)
        if not terms:
            return []

        win = self._physical_window_rect(int(hwnd))
        width = max(1, int(win.right - win.left))
        height = max(1, int(win.bottom - win.top))
        candidates = []
        ignored = {
            "what do you want to play", "search", "your library", "home",
            "play", "pause", "next", "previous", "shuffle", "repeat",
        }
        for item in snapshot.get("elements") or []:
            name = str(item.get("name") or "").strip()
            normalized = self._spotify_norm(name)
            if not name or normalized in ignored or not item.get("enabled", True):
                continue
            if not any(term in normalized for term in terms):
                continue
            rect = item.get("rect") or {}
            left = int(rect.get("left", 0) or 0)
            top = int(rect.get("top", 0) or 0)
            item_width = int(rect.get("width", 0) or 0)
            item_height = int(rect.get("height", 0) or 0)
            if item_width <= 0 or item_height <= 0:
                continue
            cx = left + item_width / 2
            cy = top + item_height / 2
            rx = (cx - int(win.left)) / width
            ry = (cy - int(win.top)) / height
            if ry >= 0.82:
                continue

            score = 0.0
            if normalized == phrase:
                score += 12.0
            if phrase and phrase in normalized:
                score += 8.0
            matched = sum(1 for term in terms if term in normalized)
            score += matched * 3.5
            if matched == len(terms):
                score += 4.0
            role = self._spotify_norm(item.get("role") or "")
            if role in {"listitem", "dataitem", "hyperlink", "button", "text", "group"}:
                score += 1.5
            if 0.22 <= rx <= 0.97:
                score += 2.0
            elif rx < 0.22:
                score -= 3.5
            if 0.10 <= ry <= 0.76:
                score += 2.0
            if "library" in normalized or "recent" in normalized:
                score -= 2.0
            if score >= 6.0:
                candidates.append((score, item))

        candidates.sort(
            key=lambda pair: (pair[0], -int(pair[1].get("index", 0) or 0)),
            reverse=True,
        )
        results = []
        seen = set()
        for score, item in candidates:
            key = self._spotify_norm(item.get("name") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            results.append({**item, "match_score": round(score, 3)})
            if len(results) >= max(1, min(int(limit), 8)):
                break
        return results

    def _spotify_find_query_result(self, hwnd: int, query: str) -> dict | None:
        results = self._spotify_find_query_results(hwnd, query, limit=1)
        return results[0] if results else None

    def _spotify_find_content_play_button(
        self,
        hwnd: int,
        *,
        anchor_name: str | None = None,
    ) -> dict | None:
        """Find a content Play control, preferring one near the selected result title."""
        snapshot = self._spotify_semantic_snapshot(hwnd)
        win = self._physical_window_rect(int(hwnd))
        width = max(1, int(win.right - win.left))
        height = max(1, int(win.bottom - win.top))

        anchor = None
        wanted = self._spotify_norm(anchor_name or "")
        if wanted:
            for item in snapshot.get("elements") or []:
                name = self._spotify_norm(item.get("name") or "")
                rect = item.get("rect") or {}
                if wanted and (name == wanted or wanted in name or name in wanted):
                    w = int(rect.get("width", 0) or 0)
                    h = int(rect.get("height", 0) or 0)
                    if w > 0 and h > 0:
                        anchor = (
                            int(rect.get("left", 0) or 0) + w / 2,
                            int(rect.get("top", 0) or 0) + h / 2,
                        )
                        break

        choices = []
        for item in snapshot.get("elements") or []:
            name = self._spotify_norm(item.get("name") or "")
            if not (name == "play" or name.startswith("play ") or " play " in f" {name} "):
                continue
            if name.startswith("playback"):
                continue
            rect = item.get("rect") or {}
            left = int(rect.get("left", 0) or 0)
            top = int(rect.get("top", 0) or 0)
            item_width = int(rect.get("width", 0) or 0)
            item_height = int(rect.get("height", 0) or 0)
            if item_width <= 0 or item_height <= 0:
                continue
            cx = left + item_width / 2
            cy = top + item_height / 2
            rx = (cx - int(win.left)) / width
            ry = (cy - int(win.top)) / height
            if ry >= 0.80 or rx < 0.20:
                continue
            role = self._spotify_norm(item.get("role") or "")
            score = 4.0
            if role == "button":
                score += 4.0
            if name == "play":
                score += 2.0
            if 0.25 <= rx <= 0.90 and 0.12 <= ry <= 0.76:
                score += 2.0
            if anchor is not None:
                dx = (cx - anchor[0]) / width
                dy = (cy - anchor[1]) / height
                distance = (dx * dx + dy * dy) ** 0.5
                score += max(0.0, 6.0 - distance * 14.0)
            choices.append((score, item))
        if not choices:
            return None
        choices.sort(
            key=lambda pair: (pair[0], -int(pair[1].get("index", 0) or 0)),
            reverse=True,
        )
        score, item = choices[0]
        return {**item, "match_score": round(score, 3)}

    def _wait_for_spotify_playback(
        self,
        hwnd: int,
        query: str,
        *,
        timeout: float = 5.0,
    ) -> dict:
        deadline = time.monotonic() + max(1.0, float(timeout))
        last = None
        while time.monotonic() < deadline:
            last = self._verify_spotify_playback(int(hwnd), query)
            if last.get("verified") or last.get("spotify_error"):
                return last
            time.sleep(0.35)
        return last or self._verify_spotify_playback(int(hwnd), query)

    def spotify_play(
        self,
        query: str,
    ) -> dict:
        query = " ".join(str(query or "").strip().split())
        if not query:
            raise ValueError("Spotify play requires a song or search query.")
        if len(query) > 220:
            raise PermissionError("Spotify query is too long.")

        focused = self.focus_app("spotify", ensure_open=True)
        hwnd = int(focused["window"])
        startup_ready = self._wait_for_spotify_ui_ready(
            hwnd,
            minimum_wait=(1.50 if focused.get("launched") else 0.35),
            timeout=(15.0 if focused.get("launched") else 6.0),
            phase="startup",
        )

        # A stale Quick Search overlay from a previous attempt can intercept all
        # subsequent clicks. Clear it before opening a deterministic search page.
        initial_overlay = self._dismiss_spotify_quick_search_overlay(hwnd)

        deep_link_opened = False
        search_ready = {}
        search_mode = "uri_search_semantic"

        def open_search_surface() -> tuple[list[dict], dict, str, bool]:
            nonlocal hwnd, focused
            used_uri = self._open_spotify_search_uri(query)
            if used_uri:
                focused = self.focus_app("spotify", ensure_open=True)
                hwnd = int(focused["window"])
                ready = self._wait_for_spotify_ui_ready(
                    hwnd,
                    minimum_wait=1.10,
                    timeout=8.0,
                    phase="uri_search_results",
                )
                results = self._spotify_find_query_results(hwnd, query, limit=4)
                if results:
                    return results, ready, "uri_search_semantic", True

            # Fallback for Spotify builds where the search URI is not handled.
            if not self._force_foreground(int(hwnd)):
                raise RuntimeError("Spotify lost foreground focus before search.")
            self.hotkey(["ctrl", "k"])
            time.sleep(0.20)
            self.hotkey(["ctrl", "a"])
            time.sleep(0.05)
            self.type_text(query)
            ready = self._wait_for_spotify_ui_ready(
                hwnd,
                minimum_wait=0.95,
                timeout=6.0,
                phase="quick_search_results",
            )
            results = self._spotify_find_query_results(hwnd, query, limit=4)
            if not results:
                self.press("enter")
                ready = self._wait_for_spotify_ui_ready(
                    hwnd,
                    minimum_wait=0.90,
                    timeout=5.0,
                    phase="full_search_results",
                )
                results = self._spotify_find_query_results(hwnd, query, limit=4)
            return results, ready, "quick_search_semantic", bool(used_uri)

        results, search_ready, search_mode, deep_link_opened = open_search_surface()
        if not results:
            raise RuntimeError(
                f"Spotify produced no visible semantic result related to {query!r}. "
                "No blind Play, Space, or media-resume command was sent."
            )

        candidate_names = []
        for item in results:
            name = str(item.get("name") or "").strip()
            if name and name not in candidate_names:
                candidate_names.append(name)

        attempt_log = []
        success = None

        for candidate_name in candidate_names[:4]:
            # Reopen search before every candidate so stale UIA bounds from a
            # previous navigation can never be reused on a different page.
            results, search_ready, search_mode, used_uri = open_search_surface()
            deep_link_opened = bool(deep_link_opened or used_uri)
            candidate = None
            wanted = self._spotify_norm(candidate_name)
            for item in results:
                if self._spotify_norm(item.get("name") or "") == wanted:
                    candidate = item
                    break
            if candidate is None:
                attempt_log.append({
                    "candidate": candidate_name,
                    "error": "candidate disappeared after search refresh",
                })
                continue

            selection_method = "uia_invoke_result"
            selected = None
            selection_invoke = None
            selection_click = None
            try:
                selection_invoke = self._invoke_spotify_observed_element(hwnd, candidate)
                selected = {
                    "name": candidate_name,
                    "role": candidate.get("role"),
                    "match_score": candidate.get("match_score"),
                }
            except Exception as exc:
                selection_invoke = {"error": f"{type(exc).__name__}: {exc}"}
                selection_method = "semantic_click_result"
                try:
                    selection_click = self._click_spotify_observed_element(hwnd, candidate, count=1)
                    selected = selection_click
                except Exception as click_exc:
                    attempt_log.append({
                        "candidate": candidate_name,
                        "selection_method": selection_method,
                        "error": f"selection failed: {type(click_exc).__name__}: {click_exc}",
                    })
                    continue

            self._wait_for_spotify_ui_ready(
                hwnd,
                minimum_wait=0.75,
                timeout=4.5,
                phase="selected_result",
            )

            overlay = self._dismiss_spotify_quick_search_overlay(hwnd)
            if overlay.get("present_before") and not overlay.get("dismissed"):
                attempt_log.append({
                    "candidate": candidate_name,
                    "selection_method": selection_method,
                    "error": "Quick Search overlay remained open",
                })
                continue
            if overlay.get("present_before"):
                self._wait_for_spotify_ui_ready(
                    hwnd,
                    minimum_wait=0.45,
                    timeout=3.5,
                    phase="after_quick_search_dismiss",
                )

            # Some Spotify result controls start playback as their default
            # action. Verify before looking for a page-level Play control.
            verification = self._wait_for_spotify_playback(hwnd, query, timeout=1.6)
            if verification.get("verified"):
                success = {
                    "candidate": candidate_name,
                    "selected": selected,
                    "selection_method": selection_method,
                    "selection_invoke": selection_invoke,
                    "selection_click": selection_click,
                    "overlay": overlay,
                    "playback_method": selection_method,
                    "play_invoke": None,
                    "play_click": None,
                    "verification": verification,
                }
                break
            if verification.get("spotify_error"):
                attempt_log.append({
                    "candidate": candidate_name,
                    "selection_method": selection_method,
                    "spotify_error": verification.get("spotify_error"),
                })
                continue

            play_button = self._spotify_find_content_play_button(
                hwnd,
                anchor_name=candidate_name,
            )
            if play_button is None:
                attempt_log.append({
                    "candidate": candidate_name,
                    "selection_method": selection_method,
                    "error": "no query-anchored content Play control was visible",
                })
                continue

            play_invoke = None
            play_click = None
            play_method = "uia_invoke_content_play_button"
            try:
                play_invoke = self._invoke_spotify_observed_element(hwnd, play_button)
                verification = self._wait_for_spotify_playback(hwnd, query, timeout=4.5)
            except Exception as exc:
                play_invoke = {"error": f"{type(exc).__name__}: {exc}"}
                verification = self._verify_spotify_playback(hwnd, query)

            if not verification.get("verified") and not verification.get("spotify_error"):
                try:
                    play_click = self._click_spotify_observed_element(hwnd, play_button, count=1)
                    play_method = "semantic_content_play_button"
                    verification = self._wait_for_spotify_playback(hwnd, query, timeout=4.5)
                except Exception as exc:
                    play_click = {"error": f"{type(exc).__name__}: {exc}"}

            if verification.get("verified"):
                success = {
                    "candidate": candidate_name,
                    "selected": selected,
                    "selection_method": selection_method,
                    "selection_invoke": selection_invoke,
                    "selection_click": selection_click,
                    "overlay": overlay,
                    "playback_method": play_method,
                    "play_invoke": play_invoke,
                    "play_click": play_click,
                    "verification": verification,
                }
                break

            attempt_log.append({
                "candidate": candidate_name,
                "selection_method": selection_method,
                "playback_method": play_method,
                "spotify_error": verification.get("spotify_error"),
                "playing": verification.get("playing"),
                "query_match": verification.get("query_match"),
                "now_playing_candidates": verification.get("now_playing_candidates", []),
            })

        if success is None:
            last = attempt_log[-1] if attempt_log else {}
            print(
                "[IRAS SPOTIFY] "
                f"query={query!r} launched={focused.get('launched', False)} "
                f"startup_wait_ms={startup_ready.get('waited_ms')} "
                f"search_mode={search_mode} verified=False attempts={len(attempt_log)} "
                f"last_error={last.get('spotify_error') or last.get('error')!r}",
                flush=True,
            )
            raise RuntimeError(
                "Spotify search succeeded, but IRAS could not verify query-matched playback. "
                "It rejected unrelated playback and Spotify error states instead of using global Space/media-resume fallbacks."
            )

        verification = success["verification"]
        selected = success["selected"]
        print(
            "[IRAS SPOTIFY] "
            f"query={query!r} launched={focused.get('launched', False)} "
            f"startup_wait_ms={startup_ready.get('waited_ms')} "
            f"search_mode={search_mode} selected={success.get('candidate')!r} "
            f"method={success.get('playback_method')} verified={verification.get('verified')} "
            f"playing={verification.get('playing')} query_match={verification.get('query_match')}",
            flush=True,
        )

        return {
            "app": "spotify",
            "query": query,
            "launched": bool(focused.get("launched")),
            "deep_link_opened": deep_link_opened,
            "foreground_verified": focused.get("foreground_verified", False),
            "startup_ready": startup_ready,
            "search_ready": search_ready,
            "search_mode": search_mode,
            "selected_result": selected,
            "selected_candidate": success.get("candidate"),
            "selection_method": success.get("selection_method"),
            "search_input_sent": True,
            "playback_method": success.get("playback_method"),
            "initial_quick_search_overlay": initial_overlay,
            "quick_search_overlay": success.get("overlay"),
            "semantic_result_invoke": success.get("selection_invoke"),
            "semantic_result_click": success.get("selection_click"),
            "semantic_play_invoke": success.get("play_invoke"),
            "semantic_play_click": success.get("play_click"),
            "semantic_play_key": None,
            "visual_green_play": None,
            "quick_search_play_sent": False,
            "quick_search_shortcut": None,
            "media_play_sent": False,
            "command_sent": True,
            "verified_playback": True,
            "playback_verification": verification,
            "now_playing_candidates": verification.get("now_playing_candidates", []),
            "query_evidence": verification.get("query_evidence", []),
            "candidate_attempts": attempt_log,
            "note": (
                "IRAS opened Spotify's deterministic search surface, selected a query-matched result, "
                "activated only controls tied to that result, rejected Spotify error toasts/unrelated playback, "
                "and required query evidence in the now-playing surface before reporting success."
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
