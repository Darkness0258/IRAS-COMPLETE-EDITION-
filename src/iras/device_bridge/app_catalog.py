from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import csv
import ctypes
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


def normalize_app_name(value: str) -> str:
    text = (
        str(value or "")
        .strip()
        .strip('"')
        .strip("'")
        .lower()
    )
    text = re.sub(
        r"\.exe$",
        "",
        text,
    )
    text = (
        text
        .replace("_", " ")
        .replace("-", " ")
    )
    text = re.sub(
        r"[^a-z0-9.+ ]+",
        " ",
        text,
    )
    return " ".join(
        text.split()
    )


def app_family_name(value: str) -> str:
    """
    Collapse version/build suffixes so e.g.:
      Blender 5.2
      Blender 5.2.1.0
    are treated as the same application family.

    This avoids rejecting perfectly valid installed apps as "ambiguous" just
    because Windows exposes multiple versioned Start-menu entries.
    """
    value = normalize_app_name(
        value
    )

    value = re.sub(
        r"\s+(?:x64|x86|64 bit|32 bit|wow)$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\s+v?\d+(?:\.\d+){0,4}$",
        "",
        value,
        flags=re.IGNORECASE,
    )

    return value.strip()


BLOCKED_APP_NAMES = {
    "cmd",
    "command prompt",
    "powershell",
    "windows powershell",
    "pwsh",
    "windows terminal",
    "terminal",
    "regedit",
    "registry editor",
    "mmc",
    "wsl",
    "bash",
    "python",
    "python3",
    "task scheduler",
    "services",
    "group policy editor",
    "local security policy",
    "anaconda prompt",
}

BLOCKED_APP_PHRASES = (
    "powershell",
    "command prompt",
    "windows terminal",
    "anaconda prompt",
    "developer command prompt",
    "native tools command prompt",
    "registry editor",
    "local security policy",
    "group policy editor",
)

BLOCKED_PROCESS_NAMES = {
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "windowsterminal",
    "windowsterminal.exe",
    "wt",
    "wt.exe",
    "regedit",
    "regedit.exe",
    "mmc",
    "mmc.exe",
    "wsl",
    "wsl.exe",
    "bash",
    "bash.exe",
    "python",
    "python.exe",
    "python3",
    "python3.exe",
}

ALIASES = {
    "edge": "microsoft edge",
    "ms edge": "microsoft edge",
    "chrome": "google chrome",
    "firefox": "mozilla firefox",
    "vlc": "vlc media player",
    "vs code": "visual studio code",
    "vscode": "visual studio code",
    "code": "visual studio code",
    "explorer": "file explorer",
    "calc": "calculator",
}


def ensure_safe_app_request(
    value: str,
) -> str:
    normalized = (
        normalize_app_name(
            value
        )
    )

    if not normalized:
        raise ValueError(
            "Application name is empty."
        )

    parts = set(
        normalized.split()
    )

    blocked = (
        normalized
        in BLOCKED_APP_NAMES
        or any(
            normalized.startswith(
                name + " "
            )
            for name in (
                BLOCKED_APP_NAMES
            )
        )
        or any(
            phrase in normalized
            for phrase in (
                BLOCKED_APP_PHRASES
            )
        )
        or bool(
            parts
            & {
                "cmd",
                "pwsh",
                "regedit",
                "wsl",
                "bash",
                "python",
                "python3",
                "mmc",
            }
        )
    )

    if blocked:
        raise PermissionError(
            f"Remote launch/control of '{value}' is blocked because it "
            "could expose a command shell or administrative console."
        )

    return normalized


@dataclass(frozen=True)
class AppEntry:
    name: str
    target: str
    kind: str
    source: str
    process_hint: str = ""

    @property
    def normalized_name(
        self,
    ) -> str:
        return normalize_app_name(
            self.name
        )

    @property
    def family_name(
        self,
    ) -> str:
        return app_family_name(
            self.name
        )

    def as_dict(
        self,
    ) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "source": self.source,
            "process_hint": (
                self.process_hint
                or None
            ),
            "family": self.family_name,
        }


class AppCatalog:
    CACHE_SECONDS = 90.0

    # Direct App Paths executables are normally the most deterministic launch
    # path, followed by Windows AppsFolder AUMIDs.
    KIND_PRIORITY = {
        "exe": 30,
        "app_id": 20,
    }

    def __init__(
        self,
    ):
        self._cached_entries: list[
            AppEntry
        ] = []
        self._cached_at = 0.0

    @staticmethod
    def _score(
        query: str,
        candidate: str,
    ) -> float:
        q = normalize_app_name(
            query
        )
        c = normalize_app_name(
            candidate
        )

        if not q or not c:
            return 0.0

        if q == c:
            return 1.0

        q_family = (
            app_family_name(
                q
            )
        )
        c_family = (
            app_family_name(
                c
            )
        )

        if (
            q_family
            and q_family
            == c_family
        ):
            return 0.97

        if (
            c.startswith(
                q + " "
            )
            or q.startswith(
                c + " "
            )
        ):
            return 0.94

        if (
            q in c
            or c in q
        ):
            return 0.88

        q_tokens = set(
            q.split()
        )
        c_tokens = set(
            c.split()
        )

        overlap = 0.0

        if (
            q_tokens
            and c_tokens
        ):
            overlap = (
                len(
                    q_tokens
                    & c_tokens
                )
                / len(
                    q_tokens
                    | c_tokens
                )
            )

        sequence = (
            SequenceMatcher(
                None,
                q,
                c,
            ).ratio()
        )

        return (
            sequence * 0.72
            + overlap * 0.28
        )

    @classmethod
    def ranked_matches(
        cls,
        query: str,
        entries: list[AppEntry],
        *,
        limit: int = 12,
    ) -> list[
        tuple[float, AppEntry]
    ]:
        normalized = (
            ensure_safe_app_request(
                query
            )
        )

        alias_target = (
            ALIASES.get(
                normalized,
                normalized,
            )
        )

        query_family = (
            app_family_name(
                alias_target
            )
        )

        scored = []

        for entry in entries:
            try:
                ensure_safe_app_request(
                    entry.name
                )
            except Exception:
                continue

            scores = [
                cls._score(
                    alias_target,
                    entry.name,
                ),
                cls._score(
                    normalized,
                    entry.name,
                ),
            ]

            if entry.process_hint:
                scores.append(
                    cls._score(
                        normalized,
                        Path(
                            entry.process_hint
                        ).stem,
                    )
                )

            score = max(
                scores
            )

            if (
                query_family
                and query_family
                == entry.family_name
            ):
                score = max(
                    score,
                    0.97,
                )

            if score < 0.58:
                continue

            scored.append(
                (
                    score,
                    entry,
                )
            )

        scored.sort(
            key=lambda item: (
                item[0],
                cls.KIND_PRIORITY.get(
                    item[1].kind,
                    0,
                ),
                -len(
                    item[1].name
                ),
            ),
            reverse=True,
        )

        return scored[
            :max(
                1,
                int(limit),
            )
        ]

    @classmethod
    def best_match(
        cls,
        query: str,
        entries: list[AppEntry],
    ) -> AppEntry:
        scored = cls.ranked_matches(
            query,
            entries,
        )

        if not scored:
            raise FileNotFoundError(
                f"No safe installed application matched '{query}'."
            )

        best_score, best = (
            scored[0]
        )

        if best_score < 0.64:
            raise FileNotFoundError(
                f"IRAS could not confidently match installed app '{query}'."
            )

        if len(scored) > 1:
            second_score, second = (
                scored[1]
            )

            # Multiple Windows entries for the same application family are
            # fallback launch methods, not ambiguity.
            same_family = (
                best.family_name
                and best.family_name
                == second.family_name
            )

            if (
                not same_family
                and best_score < 0.96
                and second_score >= 0.72
                and (
                    best_score
                    - second_score
                )
                < 0.035
                and (
                    best.normalized_name
                    != second.normalized_name
                )
            ):
                raise ValueError(
                    "Application name is ambiguous. Closest matches: "
                    f"{best.name}, {second.name}."
                )

        return best

    @staticmethod
    def _run_start_app_discovery(
    ) -> list[AppEntry]:
        if os.name != "nt":
            return []

        executable = (
            shutil.which(
                "powershell.exe"
            )
            or shutil.which(
                "powershell"
            )
        )

        if not executable:
            return []

        # Fixed command only. User text is never inserted into this shell.
        command = (
            "Get-StartApps | "
            "Select-Object Name,AppID | "
            "ConvertTo-Json -Compress"
        )

        try:
            result = subprocess.run(
                [
                    executable,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    command,
                ],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=12,
                shell=False,
            )
        except Exception:
            return []

        if (
            result.returncode
            != 0
            or not result.stdout.strip()
        ):
            return []

        try:
            payload = json.loads(
                result.stdout
            )
        except Exception:
            return []

        if isinstance(
            payload,
            dict,
        ):
            payload = [
                payload
            ]

        if not isinstance(
            payload,
            list,
        ):
            return []

        entries = []

        for item in payload:
            if not isinstance(
                item,
                dict,
            ):
                continue

            name = str(
                item.get(
                    "Name",
                    "",
                )
            ).strip()

            app_id = str(
                item.get(
                    "AppID",
                    "",
                )
            ).strip()

            if (
                not name
                or not app_id
            ):
                continue

            try:
                ensure_safe_app_request(
                    name
                )
            except Exception:
                continue

            entries.append(
                AppEntry(
                    name=name,
                    target=app_id,
                    kind="app_id",
                    source="start_apps",
                )
            )

        return entries

    @staticmethod
    def _registry_app_paths(
    ) -> list[AppEntry]:
        if os.name != "nt":
            return []

        try:
            import winreg
        except Exception:
            return []

        entries = []

        roots = [
            winreg.HKEY_CURRENT_USER,
            winreg.HKEY_LOCAL_MACHINE,
        ]

        views = [
            0,
        ]

        for name in (
            "KEY_WOW64_64KEY",
            "KEY_WOW64_32KEY",
        ):
            value = getattr(
                winreg,
                name,
                0,
            )

            if (
                value
                and value not in views
            ):
                views.append(
                    value
                )

        key_path = (
            r"Software\Microsoft\Windows"
            r"\CurrentVersion\App Paths"
        )

        for root in roots:
            for view in views:
                try:
                    parent = (
                        winreg.OpenKey(
                            root,
                            key_path,
                            0,
                            winreg.KEY_READ
                            | view,
                        )
                    )
                except OSError:
                    continue

                try:
                    index = 0

                    while True:
                        try:
                            child_name = (
                                winreg.EnumKey(
                                    parent,
                                    index,
                                )
                            )
                        except OSError:
                            break

                        index += 1

                        try:
                            child = (
                                winreg.OpenKey(
                                    parent,
                                    child_name,
                                )
                            )

                            target, _kind = (
                                winreg.QueryValueEx(
                                    child,
                                    None,
                                )
                            )

                            child.Close()
                        except OSError:
                            continue

                        target = (
                            str(
                                target
                                or ""
                            )
                            .strip()
                            .strip('"')
                        )

                        if not target:
                            continue

                        target_name = (
                            Path(
                                target
                            ).name.lower()
                        )

                        if (
                            target_name
                            in BLOCKED_PROCESS_NAMES
                        ):
                            continue

                        display = (
                            Path(
                                child_name
                            ).stem
                        )

                        try:
                            ensure_safe_app_request(
                                display
                            )
                        except Exception:
                            continue

                        entries.append(
                            AppEntry(
                                name=display,
                                target=target,
                                kind="exe",
                                source="app_paths",
                                process_hint=(
                                    Path(
                                        target
                                    ).name
                                ),
                            )
                        )
                finally:
                    parent.Close()

        return entries

    @staticmethod
    def _tasklist_names(
    ) -> set[str]:
        if os.name != "nt":
            return set()

        try:
            result = subprocess.run(
                [
                    "tasklist",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=5,
                shell=False,
            )
        except Exception:
            return set()

        if result.returncode != 0:
            return set()

        names = set()

        try:
            reader = csv.reader(
                io.StringIO(
                    result.stdout
                )
            )

            for row in reader:
                if row:
                    names.add(
                        str(
                            row[0]
                        ).strip().lower()
                    )
        except Exception:
            return set()

        return names

    @staticmethod
    def _foreground_title(
    ) -> str:
        if os.name != "nt":
            return ""

        try:
            user32 = (
                ctypes.windll.user32
            )
            hwnd = (
                user32.GetForegroundWindow()
            )

            if not hwnd:
                return ""

            length = (
                user32.GetWindowTextLengthW(
                    hwnd
                )
            )

            if length <= 0:
                return ""

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

            return (
                buffer.value.strip()
            )
        except Exception:
            return ""

    @staticmethod
    def _title_matches(
        title: str,
        app_name: str,
    ) -> bool:
        title_norm = (
            normalize_app_name(
                title
            )
        )
        app_norm = (
            normalize_app_name(
                app_name
            )
        )
        family = (
            app_family_name(
                app_name
            )
        )

        if not title_norm:
            return False

        if (
            app_norm
            and app_norm
            in title_norm
        ):
            return True

        family_tokens = [
            token
            for token in family.split()
            if len(token) >= 3
        ]

        return bool(
            family_tokens
            and all(
                token in title_norm
                for token in family_tokens
            )
        )

    @classmethod
    def _verify_launch(
        cls,
        entry: AppEntry,
        *,
        timeout: float = 2.4,
    ) -> tuple[bool, str]:
        deadline = (
            time.monotonic()
            + max(
                0.5,
                float(timeout),
            )
        )

        process_hint = (
            entry.process_hint
            .strip()
            .lower()
        )

        while (
            time.monotonic()
            < deadline
        ):
            if (
                process_hint
                and process_hint
                in cls._tasklist_names()
            ):
                return (
                    True,
                    "process",
                )

            title = (
                cls._foreground_title()
            )

            if cls._title_matches(
                title,
                entry.name,
            ):
                return (
                    True,
                    "foreground_window",
                )

            time.sleep(
                0.25
            )

        return (
            False,
            "accepted_unverified",
        )

    @staticmethod
    def _launch_exe(
        entry: AppEntry,
    ) -> dict:
        path = Path(
            entry.target
        )

        if not path.exists():
            raise FileNotFoundError(
                path
            )

        target_name = (
            path.name.lower()
        )

        if (
            target_name
            in BLOCKED_PROCESS_NAMES
        ):
            raise PermissionError(
                f"Blocked executable: {path.name}"
            )

        process = subprocess.Popen(
            [
                str(path),
            ],
            shell=False,
        )

        time.sleep(
            0.20
        )

        rc = process.poll()

        if (
            rc is not None
            and rc not in {
                0,
            }
        ):
            raise RuntimeError(
                f"{path.name} exited immediately with code {rc}."
            )

        return {
            "launched": str(
                path
            ),
            "pid": process.pid,
            "method": "direct_exe",
        }

    @staticmethod
    def _launch_app_id(
        entry: AppEntry,
    ) -> dict:
        target = (
            "shell:AppsFolder\\"
            + entry.target
        )

        shell_execute_error = None

        # ShellExecuteW handles AppsFolder/AUMID launches more directly than
        # treating explorer.exe itself as the launched application process.
        try:
            result = (
                ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "open",
                    target,
                    None,
                    None,
                    1,
                )
            )

            if int(
                result
            ) > 32:
                return {
                    "launched": target,
                    "method": (
                        "shell_execute_app_id"
                    ),
                }

            shell_execute_error = (
                f"ShellExecuteW returned {int(result)}"
            )
        except Exception as exc:
            shell_execute_error = (
                f"{type(exc).__name__}: {exc}"
            )

        # Safe fallback. No user text is executed as a shell command.
        explorer = (
            shutil.which(
                "explorer.exe"
            )
            or str(
                Path(
                    os.getenv(
                        "WINDIR",
                        r"C:\Windows",
                    )
                )
                / "explorer.exe"
            )
        )

        process = subprocess.Popen(
            [
                explorer,
                target,
            ],
            shell=False,
        )

        return {
            "launched": target,
            "pid": process.pid,
            "method": (
                "explorer_app_id"
            ),
            "shell_execute_error": (
                shell_execute_error
            ),
        }

    def refresh(
        self,
        *,
        force: bool = False,
    ) -> list[AppEntry]:
        now = (
            time.monotonic()
        )

        if (
            not force
            and self._cached_entries
            and (
                now
                - self._cached_at
            )
            < self.CACHE_SECONDS
        ):
            return list(
                self._cached_entries
            )

        entries = (
            self._run_start_app_discovery()
            + self._registry_app_paths()
        )

        # Keep alternate launch methods for the same display name. They are
        # useful fallbacks, but remove exact duplicate source targets.
        unique: dict[
            tuple[str, str, str],
            AppEntry,
        ] = {}

        for entry in entries:
            key = (
                entry.normalized_name,
                entry.kind,
                entry.target.lower(),
            )

            if key not in unique:
                unique[
                    key
                ] = entry

        self._cached_entries = (
            sorted(
                unique.values(),
                key=lambda item: (
                    item.name.lower(),
                    -self.KIND_PRIORITY.get(
                        item.kind,
                        0,
                    ),
                ),
            )
        )

        self._cached_at = now

        return list(
            self._cached_entries
        )

    def resolve(
        self,
        query: str,
    ) -> AppEntry:
        return self.best_match(
            query,
            self.refresh(),
        )

    def diagnose(
        self,
        query: str,
        *,
        limit: int = 8,
    ) -> list[dict]:
        matches = self.ranked_matches(
            query,
            self.refresh(
                force=True
            ),
            limit=limit,
        )

        return [
            {
                "score": round(
                    score,
                    4,
                ),
                **entry.as_dict(),
            }
            for score, entry in matches
        ]

    def list_apps(
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

        entries = self.refresh()

        if query:
            entries = [
                item[1]
                for item in (
                    self.ranked_matches(
                        query,
                        entries,
                        limit=limit,
                    )
                )
            ]

        return [
            entry.as_dict()
            for entry in entries[
                :limit
            ]
        ]

    def launch(
        self,
        query: str,
    ) -> dict:
        ensure_safe_app_request(
            query
        )

        if os.name != "nt":
            raise RuntimeError(
                "Automatic installed-app launch is Windows-only."
            )

        matches = (
            self.ranked_matches(
                query,
                self.refresh(
                    force=True
                ),
                limit=12,
            )
        )

        if not matches:
            raise FileNotFoundError(
                f"No safe installed application matched '{query}'."
            )

        best_score = (
            matches[0][0]
        )

        if best_score < 0.64:
            raise FileNotFoundError(
                f"IRAS could not confidently match installed app '{query}'."
            )

        best_family = (
            matches[0][1]
            .family_name
        )

        # Try alternate launch records for the same resolved application
        # family before giving up.
        candidates = [
            (
                score,
                entry,
            )
            for score, entry
            in matches
            if (
                score >= 0.64
                and (
                    entry.family_name
                    == best_family
                    or entry.normalized_name
                    == matches[0][1]
                    .normalized_name
                )
            )
        ]

        attempts = []
        accepted_result = None

        for score, entry in candidates:
            attempt = {
                "name": entry.name,
                "kind": entry.kind,
                "source": entry.source,
                "score": round(
                    score,
                    4,
                ),
            }

            try:
                if entry.kind == "exe":
                    result = (
                        self._launch_exe(
                            entry
                        )
                    )

                elif (
                    entry.kind
                    == "app_id"
                ):
                    result = (
                        self._launch_app_id(
                            entry
                        )
                    )

                else:
                    raise RuntimeError(
                        "Unsupported installed-app launch type."
                    )

                verified, proof = (
                    self._verify_launch(
                        entry
                    )
                )

                attempt[
                    "accepted"
                ] = True
                attempt[
                    "verified"
                ] = verified
                attempt[
                    "proof"
                ] = proof
                attempt[
                    "method"
                ] = result.get(
                    "method"
                )

                attempts.append(
                    attempt
                )

                payload = {
                    **result,
                    "app": entry.name,
                    "auto_detected": True,
                    "source": entry.source,
                    "launch_verified": (
                        verified
                    ),
                    "verification": proof,
                    "attempts": attempts,
                }

                if verified:
                    return payload

                if (
                    accepted_result
                    is None
                ):
                    accepted_result = (
                        payload
                    )

            except Exception as exc:
                attempt[
                    "accepted"
                ] = False
                attempt[
                    "error"
                ] = (
                    f"{type(exc).__name__}: {exc}"
                )
                attempts.append(
                    attempt
                )

        # A shell launch can be valid even when Windows does not expose a
        # quickly-verifiable process/window. Return accepted-but-unverified
        # only after all equivalent launch methods have been attempted.
        if accepted_result:
            accepted_result[
                "attempts"
            ] = attempts
            return accepted_result

        error_lines = [
            (
                f"{item['name']} "
                f"({item['kind']}): "
                f"{item.get('error', 'launch was not accepted')}"
            )
            for item in attempts
        ]

        raise RuntimeError(
            "IRAS found the application but every safe Windows launch method "
            "failed. "
            + " | ".join(
                error_lines
            )
        )


_CATALOG = AppCatalog()


def get_app_catalog(
) -> AppCatalog:
    return _CATALOG
