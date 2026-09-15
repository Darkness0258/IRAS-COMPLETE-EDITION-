from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import time

from iras.device_bridge.app_catalog import (
    ensure_safe_app_request,
    get_app_catalog,
    normalize_app_name,
)
from iras.device_bridge.ui_control import (
    WindowsUIController,
)
from iras.tools.system import launch_app


class UniversalWindowsController(
    WindowsUIController
):
    """
    Extends the bounded Windows UI controller with:
    - auto-detected installed/running apps,
    - generic focus/minimize/maximize/close,
    - auto-detected media targets,
    - reliable stop/pause/play transport controls.

    It keeps the existing action-count, hotkey and input safety limits from
    WindowsUIController.
    """

    MEDIA_PROCESS_HINTS = {
        "spotify.exe",
        "vlc.exe",
        "wmplayer.exe",
        "musicbee.exe",
        "foobar2000.exe",
        "potplayermini64.exe",
        "potplayermini.exe",
    }

    BROWSER_PROCESS_HINTS = {
        "chrome.exe",
        "msedge.exe",
        "firefox.exe",
        "brave.exe",
        "opera.exe",
    }

    MEDIA_TITLE_HINTS = (
        "spotify",
        "vlc",
        "youtube",
        "music",
        "media player",
        "netflix",
        "prime video",
        "soundcloud",
        "deezer",
    )

    def __init__(self):
        super().__init__()
        self.catalog = (
            get_app_catalog()
        )
        self._last_media_app = None

    @classmethod
    def canonical_app(
        cls,
        app: str,
    ) -> str:
        normalized = (
            ensure_safe_app_request(
                app
            )
        )

        static = (
            cls.APP_ALIASES.get(
                normalized
            )
        )

        return (
            static
            or normalized
        )

    def _window_process_name(
        self,
        hwnd: int,
    ) -> str:
        self._require_windows()

        user32 = self._user32()
        kernel32 = (
            ctypes.windll.kernel32
        )

        pid = wintypes.DWORD()

        user32.GetWindowThreadProcessId(
            hwnd,
            ctypes.byref(pid),
        )

        if not pid.value:
            return ""

        PROCESS_QUERY_LIMITED_INFORMATION = (
            0x1000
        )

        handle = (
            kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                pid.value,
            )
        )

        if not handle:
            return ""

        try:
            size = wintypes.DWORD(
                32768
            )
            buffer = (
                ctypes.create_unicode_buffer(
                    size.value
                )
            )

            ok = (
                kernel32.QueryFullProcessImageNameW(
                    handle,
                    0,
                    buffer,
                    ctypes.byref(
                        size
                    ),
                )
            )

            if not ok:
                return ""

            return (
                buffer.value
                .replace(
                    "/",
                    "\\",
                )
                .rsplit(
                    "\\",
                    1,
                )[-1]
                .lower()
            )
        finally:
            kernel32.CloseHandle(
                handle
            )

    def _visible_windows(
        self,
    ) -> list[dict]:
        user32 = self._user32()
        found = []

        callback_type = (
            ctypes.WINFUNCTYPE(
                wintypes.BOOL,
                wintypes.HWND,
                wintypes.LPARAM,
            )
        )

        @callback_type
        def callback(
            hwnd,
            _lparam,
        ):
            if not user32.IsWindowVisible(
                hwnd
            ):
                return True

            length = (
                user32.GetWindowTextLengthW(
                    hwnd
                )
            )

            if length <= 0:
                return True

            buffer = (
                ctypes.create_unicode_buffer(
                    length + 1
                )
            )

            user32.GetWindowTextW(
                hwnd,
                buffer,
                length + 1,
            )

            title = (
                buffer.value.strip()
            )

            if not title:
                return True

            rect = wintypes.RECT()
            area = 0

            if user32.GetWindowRect(
                hwnd,
                ctypes.byref(
                    rect
                ),
            ):
                width = max(
                    0,
                    rect.right
                    - rect.left,
                )
                height = max(
                    0,
                    rect.bottom
                    - rect.top,
                )
                area = width * height

            process = (
                self._window_process_name(
                    int(hwnd)
                )
            )

            found.append(
                {
                    "hwnd": int(
                        hwnd
                    ),
                    "title": title,
                    "process": process,
                    "area": area,
                }
            )

            return True

        user32.EnumWindows(
            callback,
            0,
        )

        return found

    def _find_window(
        self,
        app: str,
    ) -> int | None:
        canonical = (
            self.canonical_app(
                app
            )
        )
        normalized = (
            normalize_app_name(
                canonical
            )
        )

        known_needles = [
            normalize_app_name(
                item
            )
            for item in (
                self.APP_TITLES.get(
                    canonical,
                    (),
                )
            )
        ]

        process_hints = set()

        try:
            entry = (
                self.catalog.resolve(
                    canonical
                )
            )

            if entry.process_hint:
                process_hints.add(
                    entry.process_hint.lower()
                )
                process_hints.add(
                    normalize_app_name(
                        Path(
                            entry.process_hint
                        ).stem
                    )
                )
        except Exception:
            pass

        tokens = [
            token
            for token in normalized.split()
            if len(token) >= 3
        ]

        matches = []

        for item in (
            self._visible_windows()
        ):
            title_norm = (
                normalize_app_name(
                    item[
                        "title"
                    ]
                )
            )

            process = item[
                "process"
            ].lower()

            process_stem = (
                normalize_app_name(
                    Path(
                        process
                    ).stem
                )
                if process
                else ""
            )

            score = 0

            if any(
                needle
                and needle
                in title_norm
                for needle
                in known_needles
            ):
                score = max(
                    score,
                    120,
                )

            if (
                normalized
                and normalized
                in title_norm
            ):
                score = max(
                    score,
                    110,
                )

            if (
                tokens
                and all(
                    token
                    in title_norm
                    for token
                    in tokens
                )
            ):
                score = max(
                    score,
                    98,
                )

            if (
                process
                in process_hints
                or process_stem
                in process_hints
            ):
                score = max(
                    score,
                    125,
                )

            if (
                process_stem
                == normalized
            ):
                score = max(
                    score,
                    118,
                )

            if score:
                matches.append(
                    (
                        score,
                        item[
                            "area"
                        ],
                        item[
                            "hwnd"
                        ],
                    )
                )

        if not matches:
            return None

        matches.sort(
            reverse=True
        )

        return int(
            matches[0][2]
        )

    def detect_running_apps(
        self,
        *,
        query: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        limit = max(
            1,
            min(
                int(limit),
                250,
            ),
        )

        q = (
            normalize_app_name(
                query
            )
            if query
            else ""
        )

        output = []
        seen = set()

        for item in (
            self._visible_windows()
        ):
            process = (
                item[
                    "process"
                ]
                or ""
            )

            key = (
                process,
                item[
                    "title"
                ],
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            if q:
                haystack = (
                    normalize_app_name(
                        item[
                            "title"
                        ]
                    )
                    + " "
                    + normalize_app_name(
                        Path(
                            process
                        ).stem
                    )
                )

                if q not in haystack:
                    continue

            output.append(
                {
                    "title": item[
                        "title"
                    ],
                    "process": (
                        process
                        or None
                    ),
                    "window": item[
                        "hwnd"
                    ],
                }
            )

            if (
                len(output)
                >= limit
            ):
                break

        return output

    def app_control(
        self,
        app: str,
        action: str,
    ) -> dict:
        canonical = self.canonical_app(app)
        action = str(action or "").strip().lower()

        if action == "open":
            result = self.catalog.launch(canonical)
            result["action"] = "open"
            return result

        hwnd = self._find_window(canonical)
        if hwnd is None:
            raise RuntimeError(
                f"IRAS could not find an open window for '{app}'."
            )

        user32 = self._user32()

        def wait_for(predicate, timeout: float = 1.2) -> bool:
            deadline = time.monotonic() + max(0.1, float(timeout))
            while time.monotonic() < deadline:
                try:
                    if bool(predicate()):
                        return True
                except Exception:
                    return False
                time.sleep(0.05)
            try:
                return bool(predicate())
            except Exception:
                return False

        verification = {"window": int(hwnd)}

        if action == "focus":
            if not self._force_foreground(hwnd):
                raise RuntimeError(
                    f"Windows refused to focus '{app}'."
                )
            verified = wait_for(
                lambda: int(user32.GetForegroundWindow() or 0) == int(hwnd),
                timeout=0.5,
            )
            verification["foreground"] = verified

        elif action == "minimize":
            user32.ShowWindowAsync(hwnd, 6)
            verified = wait_for(lambda: bool(user32.IsIconic(hwnd)))
            verification["minimized"] = verified

        elif action == "maximize":
            user32.ShowWindowAsync(hwnd, 3)
            verified = wait_for(lambda: bool(user32.IsZoomed(hwnd)))
            verification["maximized"] = verified

        elif action == "restore":
            user32.ShowWindowAsync(hwnd, 9)
            verified = wait_for(
                lambda: (
                    bool(user32.IsWindow(hwnd))
                    and not bool(user32.IsIconic(hwnd))
                    and not bool(user32.IsZoomed(hwnd))
                )
            )
            verification["restored"] = verified

        elif action == "close":
            WM_CLOSE = 0x0010
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            verified = wait_for(
                lambda: not bool(user32.IsWindow(hwnd)),
                timeout=1.5,
            )
            verification["closed"] = verified
            if not verified:
                verification["reason"] = (
                    "The window remained open; it may be showing a save/confirmation dialog."
                )

        else:
            raise PermissionError(
                f"App action '{action}' is not allowed."
            )

        return {
            "app": canonical,
            "action": action,
            "window": hwnd,
            "command_sent": True,
            "verified_state": bool(verified),
            "verification": verification,
        }

    def spotify_search(
        self,
        query: str,
    ) -> dict:
        result = super().spotify_search(
            query
        )
        self._last_media_app = (
            "spotify"
        )
        return result

    def spotify_play(
        self,
        query: str,
    ) -> dict:
        result = super().spotify_play(
            query
        )
        self._last_media_app = (
            "spotify"
        )
        return result

    @staticmethod
    def _is_media_window(
        item: dict,
    ) -> bool:
        process = str(
            item.get(
                "process",
                "",
            )
        ).lower()

        title = str(
            item.get(
                "title",
                "",
            )
        ).lower()

        if process in (
            UniversalWindowsController
            .MEDIA_PROCESS_HINTS
        ):
            return True

        if process in (
            UniversalWindowsController
            .BROWSER_PROCESS_HINTS
        ):
            return any(
                hint in title
                for hint in (
                    UniversalWindowsController
                    .MEDIA_TITLE_HINTS
                )
            )

        return any(
            hint in title
            for hint in (
                UniversalWindowsController
                .MEDIA_TITLE_HINTS
            )
        )

    def _auto_media_target(
        self,
        app: str | None = None,
    ) -> tuple[int | None, str | None]:
        if app:
            canonical = (
                self.canonical_app(
                    app
                )
            )
            hwnd = self._find_window(
                canonical
            )

            if hwnd is not None:
                return (
                    hwnd,
                    canonical,
                )

            # Distinguish "installed but not running" from an unknown app.
            try:
                entry = (
                    self.catalog.resolve(
                        canonical
                    )
                )
                return (
                    None,
                    entry.name,
                )
            except FileNotFoundError:
                raise RuntimeError(
                    f"IRAS could not find installed/running media app '{app}'."
                )

        user32 = self._user32()
        foreground = int(
            user32.GetForegroundWindow()
            or 0
        )

        windows = (
            self._visible_windows()
        )

        by_hwnd = {
            item[
                "hwnd"
            ]: item
            for item in windows
        }

        foreground_info = (
            by_hwnd.get(
                foreground
            )
        )

        if (
            foreground_info
            and self._is_media_window(
                foreground_info
            )
        ):
            return (
                foreground,
                normalize_app_name(
                    Path(
                        foreground_info[
                            "process"
                        ]
                    ).stem
                    or foreground_info[
                        "title"
                    ]
                ),
            )

        if self._last_media_app:
            hwnd = self._find_window(
                self._last_media_app
            )

            if hwnd is not None:
                return (
                    hwnd,
                    self._last_media_app,
                )

        candidates = [
            item
            for item in windows
            if self._is_media_window(
                item
            )
        ]

        if candidates:
            candidates.sort(
                key=lambda item: (
                    item[
                        "area"
                    ]
                ),
                reverse=True,
            )

            item = candidates[0]

            label = (
                normalize_app_name(
                    Path(
                        item[
                            "process"
                        ]
                    ).stem
                )
                if item[
                    "process"
                ]
                else normalize_app_name(
                    item[
                        "title"
                    ]
                )
            )

            return (
                item[
                    "hwnd"
                ],
                label,
            )

        # Do not target an arbitrary foreground app. Generic media keys below
        # are safer than sending WM_APPCOMMAND to PowerShell/IRAS/Explorer.
        return (
            None,
            None,
        )

    def _send_global_media_key(
        self,
        action: str,
    ) -> bool:
        codes = {
            "next": 0xB0,
            "previous": 0xB1,
            "stop": 0xB2,
            "play_pause": 0xB3,
            "mute": 0xAD,
            "volume_down": 0xAE,
            "volume_up": 0xAF,
        }

        code = codes.get(
            action
        )

        if code is None:
            return False

        user32 = self._user32()

        user32.keybd_event(
            code,
            0,
            0,
            0,
        )

        time.sleep(
            0.025
        )

        user32.keybd_event(
            code,
            0,
            0x0002,
            0,
        )

        return True

    def media_control(
        self,
        command: str,
        app: str | None = None,
    ) -> dict:
        normalized = (
            " ".join(
                str(
                    command
                    or ""
                )
                .lower()
                .replace(
                    "-",
                    "_",
                )
                .split()
            )
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

        spotify_only = {
            "shuffle_toggle",
            "repeat_toggle",
            "like_toggle",
            "open_queue",
            "open_liked_songs",
            "open_now_playing",
        }

        if action in spotify_only:
            if (
                app
                and self.canonical_app(
                    app
                )
                != "spotify"
            ):
                raise PermissionError(
                    f"'{action}' is currently a Spotify-specific control."
                )

            self._last_media_app = (
                "spotify"
            )

            return super().media_control(
                action
            )

        if action in {
            "mute",
            "unmute",
            "volume_up",
            "volume_down",
        }:
            key_action = (
                "mute"
                if action
                in {
                    "mute",
                    "unmute",
                }
                else action
            )

            sent = (
                self._send_global_media_key(
                    key_action
                )
            )

            return {
                "command": action,
                "command_sent": bool(
                    sent
                ),
                "transport": (
                    "global_media_key"
                ),
                "target_app": None,
                "auto_detected": True,
                "verified_state": False,
            }

        app_commands = {
            "next": 11,
            "previous": 12,
            "stop": 13,
            "play_pause": 14,
            "play": 46,
            "pause": 47,
        }

        command_id = (
            app_commands.get(
                action
            )
        )

        if command_id is None:
            raise PermissionError(
                f"Media command '{command}' is not allowed."
            )

        hwnd, target = (
            self._auto_media_target(
                app
            )
        )

        # Pause/stop are idempotent when an explicitly requested app is not
        # running. Do not accidentally control some other media session.
        if app and hwnd is None:
            if action in {
                "pause",
                "stop",
            }:
                return {
                    "command": action,
                    "command_sent": False,
                    "transport": [],
                    "target_app": target,
                    "target_window": None,
                    "target_running": False,
                    "already_inactive": True,
                    "auto_detected": False,
                    "verified_state": False,
                    "note": (
                        f"{target or app} has no visible running window, so "
                        f"there is nothing to {action}."
                    ),
                }

            raise RuntimeError(
                f"{target or app} is installed but has no visible running "
                f"window for the {action} command."
            )

        sent = False
        transports = []

        if hwnd:
            sent = bool(
                self._send_media_appcommand(
                    command_id,
                    hwnd=hwnd,
                )
            )

            if sent:
                transports.append(
                    "wm_appcommand"
                )

        if action == "stop":
            if hwnd:
                # Dedicated STOP is inconsistently implemented. Explicit PAUSE
                # is idempotent and prevents Spotify/VLC from continuing.
                paused = bool(
                    self._send_media_appcommand(
                        47,
                        hwnd=hwnd,
                    )
                )

                if paused:
                    sent = True
                    transports.append(
                        "wm_appcommand_pause"
                    )
            else:
                if self._send_global_media_key(
                    "stop"
                ):
                    sent = True
                    transports.append(
                        "global_stop"
                    )

        elif not hwnd:
            fallback = {
                "next": "next",
                "previous": "previous",
                "play_pause": "play_pause",
                "play": "play_pause",
                "pause": "play_pause",
            }.get(
                action
            )

            if (
                fallback
                and self._send_global_media_key(
                    fallback
                )
            ):
                sent = True
                transports.append(
                    "global_media_key"
                )

        if not sent:
            raise RuntimeError(
                f"IRAS could not deliver the {action} command to an active "
                "media application."
            )

        if target:
            self._last_media_app = (
                target
            )

        return {
            "command": action,
            "command_sent": True,
            "transport": transports,
            "target_app": target,
            "target_window": hwnd,
            "target_running": bool(
                hwnd
            ),
            "auto_detected": (
                app is None
            ),
            "verified_state": False,
        }
