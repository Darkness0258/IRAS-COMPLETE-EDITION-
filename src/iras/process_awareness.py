from __future__ import annotations

import csv
import io
import json
import os
import subprocess
from collections import Counter
from pathlib import Path, PureWindowsPath
from typing import Any


_BROWSER_NAMES = {"chrome", "msedge", "firefox", "brave", "opera", "vivaldi"}
_DEV_NAMES = {
    "code", "devenv", "python", "pythonw", "node", "npm", "pnpm", "bun",
    "git", "cargo", "rustc", "java", "javaw", "gradle", "adb", "docker",
    "ollama", "cmake", "ninja",
}
_TERMINAL_NAMES = {"cmd", "powershell", "pwsh", "windowsterminal", "wt", "wsl", "bash"}
_MEDIA_NAMES = {"spotify", "vlc", "wmplayer", "musicbee", "foobar2000", "mpv"}
_COMM_NAMES = {"discord", "slack", "teams", "ms-teams", "whatsapp", "telegram", "zoom"}
_SYSTEM_NAMES = {
    "system", "registry", "smss", "csrss", "wininit", "winlogon", "services",
    "lsass", "svchost", "fontdrvhost", "dwm", "sihost", "taskhostw", "ctfmon",
    "memory compression", "secure system", "idle",
}


def _name_key(value: Any) -> str:
    raw = str(value or "").replace("/", "\\")
    name = PureWindowsPath(raw).name
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name.strip().lower()


def categorize_process(row: dict[str, Any]) -> str:
    name = _name_key(row.get("name"))
    title = str(row.get("main_window_title") or "").strip()
    if name in _SYSTEM_NAMES or name.startswith(("svchost", "runtimebroker")):
        return "system"
    if name in _BROWSER_NAMES:
        return "browser"
    if name in _DEV_NAMES:
        return "development"
    if name in _TERMINAL_NAMES:
        return "terminal"
    if name in _MEDIA_NAMES:
        return "media"
    if name in _COMM_NAMES:
        return "communication"
    if title:
        return "application"
    return "background"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return int(default)


def normalize_process_row(row: dict[str, Any], *, include_path: bool) -> dict[str, Any]:
    item = {
        "pid": _safe_int(row.get("pid")),
        "parent_pid": _safe_int(row.get("parent_pid")),
        "name": str(row.get("name") or "").strip(),
        "cpu_seconds": round(_safe_float(row.get("cpu_seconds")), 2),
        "working_set_mb": round(_safe_float(row.get("working_set_mb")), 1),
        "private_mb": round(_safe_float(row.get("private_mb")), 1),
        "threads": _safe_int(row.get("threads")),
        "handles": _safe_int(row.get("handles")),
        "session_id": _safe_int(row.get("session_id"), -1),
        "responding": bool(row.get("responding", True)),
        "main_window_title": str(row.get("main_window_title") or "").strip()[:1000],
        "start_time": str(row.get("start_time") or "").strip()[:80] or None,
    }
    if include_path:
        item["path"] = str(row.get("path") or "").strip()[:2000] or None
    item["category"] = categorize_process(item)
    item["visible_app"] = bool(item["main_window_title"])
    return item


class ProcessAwareness:
    """Structured, read-only process inventory with change tracking.

    Process command lines are intentionally not collected because they commonly
    contain access tokens, passwords, URLs with secrets, or other sensitive data.
    """

    def __init__(self):
        self._previous: dict[tuple[int, str], dict[str, Any]] = {}

    @staticmethod
    def _windows_rows(*, include_path: bool) -> list[dict[str, Any]]:
        path_block = "try { $path = [string]$p.Path } catch {}" if include_path else ""
        script = rf"""
$ErrorActionPreference = 'SilentlyContinue'
$parentMap = @{{}}
try {{ Get-CimInstance Win32_Process | ForEach-Object {{ $parentMap[[int]$_.ProcessId] = [int]$_.ParentProcessId }} }} catch {{}}
$rows = Get-Process | ForEach-Object {{
  $p = $_
  $started = $null
  try {{ $started = $p.StartTime.ToUniversalTime().ToString('o') }} catch {{}}
  $path = $null
  {path_block}
  $parent = 0
  if ($parentMap.ContainsKey([int]$p.Id)) {{ $parent = [int]$parentMap[[int]$p.Id] }}
  $cpu = 0.0
  if ($null -ne $p.CPU) {{ $cpu = [double]$p.CPU }}
  $threads = 0
  try {{ $threads = [int]$p.Threads.Count }} catch {{}}
  $handles = 0
  try {{ $handles = [int]$p.HandleCount }} catch {{}}
  $session = -1
  try {{ $session = [int]$p.SessionId }} catch {{}}
  $responding = $true
  try {{ $responding = [bool]$p.Responding }} catch {{}}
  $windowTitle = ''
  try {{ $windowTitle = [string]$p.MainWindowTitle }} catch {{}}
  [PSCustomObject]@{{
    pid = [int]$p.Id
    parent_pid = $parent
    name = [string]$p.ProcessName
    cpu_seconds = $cpu
    working_set_mb = [math]::Round(([double]$p.WorkingSet64 / 1MB), 1)
    private_mb = [math]::Round(([double]$p.PrivateMemorySize64 / 1MB), 1)
    threads = $threads
    handles = $handles
    session_id = $session
    responding = $responding
    main_window_title = $windowTitle
    start_time = $started
    path = $path
  }}
}}
$rows | ConvertTo-Json -Compress -Depth 3
"""
        cp = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
            shell=False,
        )
        if cp.returncode != 0 or not cp.stdout.strip():
            return ProcessAwareness._windows_tasklist_fallback()
        try:
            payload = json.loads(cp.stdout)
        except json.JSONDecodeError:
            return ProcessAwareness._windows_tasklist_fallback()
        if isinstance(payload, dict):
            return [payload]
        return [row for row in (payload or []) if isinstance(row, dict)]

    @staticmethod
    def _windows_tasklist_fallback() -> list[dict[str, Any]]:
        cp = subprocess.run(
            ["tasklist", "/V", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=20,
            shell=False,
        )
        rows: list[dict[str, Any]] = []
        for values in csv.reader(io.StringIO(cp.stdout)):
            if len(values) < 9:
                continue
            memory = str(values[4]).replace(",", "").replace("K", "").replace("k", "").strip()
            try:
                mb = round(int(memory) / 1024.0, 1)
            except ValueError:
                mb = 0.0
            rows.append(
                {
                    "pid": values[1],
                    "name": values[0],
                    "working_set_mb": mb,
                    "session_id": values[3],
                    "main_window_title": values[8] if values[8] != "N/A" else "",
                    "responding": values[5].lower() not in {"not responding", "unknown"},
                }
            )
        return rows

    @staticmethod
    def _posix_rows() -> list[dict[str, Any]]:
        cp = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,comm=,rss=,etimes="],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=20,
            shell=False,
        )
        rows = []
        for line in cp.stdout.splitlines():
            parts = line.strip().split(None, 4)
            if len(parts) != 5:
                continue
            pid, ppid, comm, rss, elapsed = parts
            rows.append(
                {
                    "pid": pid,
                    "parent_pid": ppid,
                    "name": comm,
                    "working_set_mb": round(_safe_float(rss) / 1024.0, 1),
                    "start_time": f"elapsed:{elapsed}s",
                    "responding": True,
                }
            )
        return rows

    def snapshot_from_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        limit: int = 300,
        query: str = "",
        only_apps: bool = False,
        sort_by: str = "memory",
        include_path: bool = False,
        track_changes: bool = True,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 1000))
        query_norm = str(query or "").strip().casefold()
        sort_by = str(sort_by or "memory").strip().lower()
        if sort_by not in {"memory", "cpu", "name", "pid"}:
            raise ValueError("sort_by must be memory, cpu, name, or pid.")

        processes = [normalize_process_row(row, include_path=include_path) for row in rows if isinstance(row, dict)]
        processes = [row for row in processes if row.get("pid", 0) > 0 and row.get("name")]
        all_processes = list(processes)

        if query_norm:
            processes = [
                row for row in processes
                if query_norm in (
                    f"{row.get('name','')} {row.get('main_window_title','')} {row.get('category','')} {row.get('path','')}"
                ).casefold()
            ]
        if only_apps:
            processes = [row for row in processes if row.get("visible_app")]

        key_fn = {
            "memory": lambda row: (-float(row.get("working_set_mb") or 0), str(row.get("name") or "").casefold()),
            "cpu": lambda row: (-float(row.get("cpu_seconds") or 0), str(row.get("name") or "").casefold()),
            "name": lambda row: (str(row.get("name") or "").casefold(), int(row.get("pid") or 0)),
            "pid": lambda row: (int(row.get("pid") or 0),),
        }[sort_by]
        processes.sort(key=key_fn)

        current = {(int(row["pid"]), _name_key(row["name"])): row for row in all_processes}
        started: list[dict[str, Any]] = []
        exited: list[dict[str, Any]] = []
        if track_changes and self._previous:
            for key in current.keys() - self._previous.keys():
                row = current[key]
                started.append({"pid": row["pid"], "name": row["name"], "category": row["category"]})
            for key in self._previous.keys() - current.keys():
                row = self._previous[key]
                exited.append({"pid": row["pid"], "name": row["name"], "category": row.get("category", "unknown")})
        if track_changes:
            self._previous = current

        category_counts = Counter(row["category"] for row in all_processes)
        visible_apps = [row for row in all_processes if row.get("visible_app")]
        not_responding = [
            {"pid": row["pid"], "name": row["name"], "title": row["main_window_title"]}
            for row in all_processes if not row.get("responding", True)
        ][:25]
        top_memory = sorted(all_processes, key=lambda row: float(row.get("working_set_mb") or 0), reverse=True)[:10]
        top_cpu = sorted(all_processes, key=lambda row: float(row.get("cpu_seconds") or 0), reverse=True)[:10]

        return {
            "process_count": len(all_processes),
            "matched_count": len(processes),
            "visible_app_count": len(visible_apps),
            "total_working_set_mb": round(sum(float(row.get("working_set_mb") or 0) for row in all_processes), 1),
            "categories": dict(sorted(category_counts.items())),
            "not_responding": not_responding,
            "top_memory": [
                {"pid": row["pid"], "name": row["name"], "working_set_mb": row["working_set_mb"], "title": row["main_window_title"]}
                for row in top_memory
            ],
            "top_cpu_time": [
                {"pid": row["pid"], "name": row["name"], "cpu_seconds": row["cpu_seconds"], "title": row["main_window_title"]}
                for row in top_cpu
            ],
            "changes": {
                "started": sorted(started, key=lambda row: (row["name"].casefold(), row["pid"]))[:50],
                "exited": sorted(exited, key=lambda row: (row["name"].casefold(), row["pid"]))[:50],
            },
            "query": query or None,
            "only_apps": bool(only_apps),
            "sort_by": sort_by,
            "include_path": bool(include_path),
            "command_lines_collected": False,
            "processes": processes[:limit],
        }

    def snapshot(
        self,
        *,
        limit: int = 300,
        query: str = "",
        only_apps: bool = False,
        sort_by: str = "memory",
        include_path: bool = False,
        track_changes: bool = True,
    ) -> dict[str, Any]:
        rows = self._windows_rows(include_path=include_path) if os.name == "nt" else self._posix_rows()
        return self.snapshot_from_rows(
            rows,
            limit=limit,
            query=query,
            only_apps=only_apps,
            sort_by=sort_by,
            include_path=include_path,
            track_changes=track_changes,
        )
