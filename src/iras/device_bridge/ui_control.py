from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import time

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
            deadline = time.monotonic() + 8.0

            while time.monotonic() < deadline:
                time.sleep(0.35)
                hwnd = self._find_window(canonical)
                if hwnd is not None:
                    break

        if hwnd is None:
            raise RuntimeError(
                f"Could not find a visible {canonical} window."
            )

        user32 = self._user32()
        user32.ShowWindow(hwnd, 9)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.20)

        return {
            "app": canonical,
            "window": hwnd,
            "launched": launched,
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
        self._set_clipboard_text(text)
        self.hotkey(["ctrl", "v"])

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
