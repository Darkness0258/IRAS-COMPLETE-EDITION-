from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


def normalize_app_name(value: str) -> str:
    text = str(value or "").strip().strip('"').strip("'").lower()
    text = re.sub(r"\.exe$", "", text)
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9.+ ]+", " ", text)
    return " ".join(text.split())


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


def ensure_safe_app_request(value: str) -> str:
    normalized = normalize_app_name(value)

    if not normalized:
        raise ValueError("Application name is empty.")

    # Paths are normalized too, so a request such as
    # C:\\Windows\\System32\\WindowsPowerShell\\... is rejected.
    parts = set(normalized.split())

    blocked = (
        normalized in BLOCKED_APP_NAMES
        or any(
            normalized.startswith(name + " ")
            for name in BLOCKED_APP_NAMES
        )
        or any(
            phrase in normalized
            for phrase in BLOCKED_APP_PHRASES
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
    def normalized_name(self) -> str:
        return normalize_app_name(self.name)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "source": self.source,
            "process_hint": self.process_hint or None,
        }


class AppCatalog:
    CACHE_SECONDS = 90.0

    def __init__(self):
        self._cached_entries: list[AppEntry] = []
        self._cached_at = 0.0

    @staticmethod
    def _score(query: str, candidate: str) -> float:
        q = normalize_app_name(query)
        c = normalize_app_name(candidate)

        if not q or not c:
            return 0.0
        if q == c:
            return 1.0
        if c.startswith(q + " ") or q.startswith(c + " "):
            return 0.94
        if q in c or c in q:
            return 0.88

        q_tokens = set(q.split())
        c_tokens = set(c.split())
        overlap = 0.0
        if q_tokens and c_tokens:
            overlap = len(q_tokens & c_tokens) / len(q_tokens | c_tokens)

        sequence = SequenceMatcher(None, q, c).ratio()
        return sequence * 0.72 + overlap * 0.28

    @classmethod
    def best_match(cls, query: str, entries: list[AppEntry]) -> AppEntry:
        normalized = ensure_safe_app_request(query)
        alias_target = ALIASES.get(normalized, normalized)
        scored = []

        for entry in entries:
            try:
                ensure_safe_app_request(entry.name)
            except Exception:
                continue

            scores = [
                cls._score(alias_target, entry.name),
                cls._score(normalized, entry.name),
            ]
            if entry.process_hint:
                scores.append(
                    cls._score(normalized, Path(entry.process_hint).stem)
                )

            scored.append((max(scores), entry))

        if not scored:
            raise FileNotFoundError(
                f"No safe installed application matched '{query}'."
            )

        scored.sort(
            key=lambda item: (item[0], len(item[1].name)),
            reverse=True,
        )
        best_score, best = scored[0]

        if best_score < 0.64:
            raise FileNotFoundError(
                f"IRAS could not confidently match installed app '{query}'."
            )

        if len(scored) > 1:
            second_score, second = scored[1]
            if (
                best_score < 0.96
                and second_score >= 0.72
                and (best_score - second_score) < 0.035
                and best.name.lower() != second.name.lower()
            ):
                raise ValueError(
                    "Application name is ambiguous. Closest matches: "
                    f"{best.name}, {second.name}."
                )

        return best

    @staticmethod
    def _run_start_app_discovery() -> list[AppEntry]:
        if os.name != "nt":
            return []

        executable = shutil.which("powershell.exe") or shutil.which("powershell")
        if not executable:
            return []

        # Fixed command only. User text is never inserted into this shell.
        command = (
            "Get-StartApps | Select-Object Name,AppID | "
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

        if result.returncode != 0 or not result.stdout.strip():
            return []

        try:
            payload = json.loads(result.stdout)
        except Exception:
            return []

        if isinstance(payload, dict):
            payload = [payload]

        entries = []
        if not isinstance(payload, list):
            return entries

        for item in payload:
            if not isinstance(item, dict):
                continue

            name = str(item.get("Name", "")).strip()
            app_id = str(item.get("AppID", "")).strip()
            if not name or not app_id:
                continue

            try:
                ensure_safe_app_request(name)
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
    def _registry_app_paths() -> list[AppEntry]:
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
        views = [0]

        for name in ("KEY_WOW64_64KEY", "KEY_WOW64_32KEY"):
            value = getattr(winreg, name, 0)
            if value and value not in views:
                views.append(value)

        key_path = (
            r"Software\Microsoft\Windows"
            r"\CurrentVersion\App Paths"
        )

        for root in roots:
            for view in views:
                try:
                    parent = winreg.OpenKey(
                        root,
                        key_path,
                        0,
                        winreg.KEY_READ | view,
                    )
                except OSError:
                    continue

                try:
                    index = 0
                    while True:
                        try:
                            child_name = winreg.EnumKey(parent, index)
                        except OSError:
                            break
                        index += 1

                        try:
                            child = winreg.OpenKey(parent, child_name)
                            target, _kind = winreg.QueryValueEx(child, None)
                            child.Close()
                        except OSError:
                            continue

                        target = str(target or "").strip().strip('"')
                        if not target:
                            continue

                        target_name = Path(target).name.lower()
                        if target_name in BLOCKED_PROCESS_NAMES:
                            continue

                        display = Path(child_name).stem
                        try:
                            ensure_safe_app_request(display)
                        except Exception:
                            continue

                        entries.append(
                            AppEntry(
                                name=display,
                                target=target,
                                kind="exe",
                                source="app_paths",
                                process_hint=Path(target).name,
                            )
                        )
                finally:
                    parent.Close()

        return entries

    def refresh(self, *, force: bool = False) -> list[AppEntry]:
        now = time.monotonic()

        if (
            not force
            and self._cached_entries
            and (now - self._cached_at) < self.CACHE_SECONDS
        ):
            return list(self._cached_entries)

        entries = self._run_start_app_discovery() + self._registry_app_paths()

        unique: dict[tuple[str, str], AppEntry] = {}
        for entry in entries:
            key = (entry.normalized_name, entry.kind)
            if key not in unique:
                unique[key] = entry

        self._cached_entries = sorted(
            unique.values(),
            key=lambda item: item.name.lower(),
        )
        self._cached_at = now
        return list(self._cached_entries)

    def resolve(self, query: str) -> AppEntry:
        return self.best_match(query, self.refresh())

    def list_apps(
        self,
        *,
        query: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 250))
        entries = self.refresh()

        if query:
            normalized = normalize_app_name(query)
            scored = [
                (self._score(normalized, entry.name), entry)
                for entry in entries
            ]
            scored = [item for item in scored if item[0] >= 0.45]
            scored.sort(key=lambda item: item[0], reverse=True)
            entries = [item[1] for item in scored]

        return [entry.as_dict() for entry in entries[:limit]]

    def launch(self, query: str) -> dict:
        entry = self.resolve(query)

        if os.name != "nt":
            raise RuntimeError(
                "Automatic installed-app launch is Windows-only."
            )

        if entry.kind == "exe":
            path = Path(entry.target)
            if not path.exists():
                raise FileNotFoundError(path)

            process = subprocess.Popen([str(path)], shell=False)
            return {
                "launched": str(path),
                "pid": process.pid,
                "app": entry.name,
                "auto_detected": True,
                "source": entry.source,
            }

        if entry.kind == "app_id":
            explorer = shutil.which("explorer.exe") or str(
                Path(os.getenv("WINDIR", r"C:\Windows")) / "explorer.exe"
            )
            process = subprocess.Popen(
                [
                    explorer,
                    "shell:AppsFolder\\" + entry.target,
                ],
                shell=False,
            )
            return {
                "launched": "shell:AppsFolder\\" + entry.target,
                "pid": process.pid,
                "app": entry.name,
                "auto_detected": True,
                "source": entry.source,
            }

        raise RuntimeError("Unsupported installed-app launch type.")


_CATALOG = AppCatalog()


def get_app_catalog() -> AppCatalog:
    return _CATALOG
