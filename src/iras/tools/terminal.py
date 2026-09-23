from __future__ import annotations

import os
from pathlib import Path
import queue
import re
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from typing import Any

from iras.models import PermissionLevel
from iras.tools.base import Tool


# Universal terminal access intentionally does not maintain a CLI-name allowlist.
# Authorization is attached to the *operation* and command risk, not whether a
# particular executable was anticipated by IRAS when the release was built.
_CRITICAL_PATTERNS = (
    r"\bformat(?:\.com)?\b",
    r"\bdiskpart\b",
    r"\bmkfs(?:\.[a-z0-9_-]+)?\b",
    r"\bdd\s+if=",
    r"\bbcdedit\b",
    r"\bbootrec\b",
    r"\breg(?:\.exe)?\s+delete\b",
    r"\b(?:shutdown|restart-computer|stop-computer)\b",
    r"\bvssadmin\s+delete\b",
    r"\bwbadmin\s+delete\b",
    r"\bsc(?:\.exe)?\s+delete\b",
    r"\bschtasks(?:\.exe)?\s+/delete\b",
    r"\b(?:rm|remove-item)\b[^\r\n]*(?:-rf|-fr|-recurse|-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)",
    r"\bdel(?:\.exe)?\b[^\r\n]*/[a-z]*[fq][a-z]*",
    r"\brmdir(?:\.exe)?\b[^\r\n]*/s\b",
    r"\bgit\s+push\b[^\r\n]*--force(?:-with-lease)?\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\b[^\r\n]*-[a-z]*f",
    r"\b(?:cipher|sdelete)\b[^\r\n]*(?:/w|-p|--passes)",
    r"\bmanage-bde\b[^\r\n]*(?:-off|-delete|-forcerecovery)",
)


def classify_terminal(args: dict[str, Any]) -> PermissionLevel:
    command = str(args.get("command") or "")
    if any(re.search(pattern, command, flags=re.IGNORECASE) for pattern in _CRITICAL_PATTERNS):
        return PermissionLevel.CRITICAL
    return PermissionLevel.SYSTEM_ACTION


def _max_output() -> int:
    try:
        value = int(os.getenv("IRAS_TERMINAL_MAX_OUTPUT", "50000"))
    except (TypeError, ValueError):
        value = 50000
    return max(4000, min(value, 250000))


def _truncate(text: str) -> str:
    text = str(text or "")
    cap = _max_output()
    if len(text) <= cap:
        return text
    return "...<truncated>...\n" + text[-cap:]


def _shell_program(shell: str) -> tuple[list[str], bool]:
    normalized = str(shell or "auto").strip().lower()
    windows = os.name == "nt"

    if normalized in {"auto", "powershell", "pwsh"}:
        if windows:
            if normalized == "pwsh":
                path = shutil.which("pwsh")
                if path:
                    return [path, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command"], False
            path = shutil.which("powershell") or shutil.which("powershell.exe") or shutil.which("pwsh")
            if path:
                args = [path, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command"]
                return args, False
        if normalized in {"powershell", "pwsh"}:
            path = shutil.which("pwsh") or shutil.which("powershell")
            if path:
                return [path, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command"], False

    if normalized in {"cmd", "cmd.exe"} and windows:
        path = shutil.which("cmd") or os.environ.get("COMSPEC") or "cmd.exe"
        return [path, "/d", "/s", "/c"], False

    if normalized in {"bash", "sh"}:
        path = shutil.which(normalized)
        if not path:
            raise RuntimeError(f"Requested shell '{normalized}' is not installed or not on PATH.")
        return [path, "-lc"], False

    if normalized == "direct":
        return [], True

    if normalized == "auto":
        if windows:
            path = os.environ.get("COMSPEC") or shutil.which("cmd") or "cmd.exe"
            return [path, "/d", "/s", "/c"], False
        path = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
        return [path, "-lc"], False

    raise ValueError("shell must be one of: auto, powershell, pwsh, cmd, bash, sh, direct")


def _direct_argv(command: str) -> list[str]:
    if os.name == "nt":
        # posix=False preserves Windows quoting rules much better than the POSIX
        # default, while still avoiding shell metacharacter interpretation.
        return shlex.split(command, posix=False)
    return shlex.split(command)


def _prepare_command(command: str, shell: str) -> tuple[list[str] | str, bool, str]:
    prefix, direct = _shell_program(shell)
    if direct:
        argv = _direct_argv(command)
        if not argv:
            raise ValueError("command is required")
        return argv, False, "direct"
    return [*prefix, command], False, Path(prefix[0]).name if prefix else "shell"


def _merge_env(env: dict[str, Any] | None) -> dict[str, str]:
    merged = dict(os.environ)
    for key, value in (env or {}).items():
        key = str(key).strip()
        if not key or "\x00" in key or "=" in key:
            raise ValueError("Invalid environment variable name.")
        merged[key] = str(value)
    return merged


def terminal_exec(
    command: str,
    cwd: str | None = None,
    timeout: int = 120,
    shell: str = "auto",
    stdin: str | None = None,
    env: dict[str, Any] | None = None,
) -> dict[str, Any]:
    command = str(command or "").strip()
    if not command:
        raise ValueError("command is required")
    timeout = max(1, min(int(timeout), 3600))
    workdir = str(Path(cwd).expanduser()) if cwd else None
    argv, use_shell, resolved_shell = _prepare_command(command, shell)
    started = time.perf_counter()
    cp = subprocess.run(
        argv,
        cwd=workdir,
        shell=use_shell,
        capture_output=True,
        text=True,
        input=stdin,
        timeout=timeout,
        errors="replace",
        env=_merge_env(env),
    )
    return {
        "returncode": int(cp.returncode),
        "stdout": _truncate(cp.stdout),
        "stderr": _truncate(cp.stderr),
        "cwd": workdir or os.getcwd(),
        "shell": resolved_shell,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def terminal_which(name: str) -> dict[str, Any]:
    raw = str(name or "").strip()
    if not raw:
        raise ValueError("name is required")
    path = shutil.which(raw)
    result: dict[str, Any] = {"name": raw, "path": path, "found": bool(path)}

    if os.name == "nt":
        ps = shutil.which("powershell") or shutil.which("powershell.exe") or shutil.which("pwsh")
        if ps:
            escaped = raw.replace("'", "''")
            script = (
                f"$c=Get-Command -Name '{escaped}' -ErrorAction SilentlyContinue | Select-Object -First 1; "
                "if($c){[pscustomobject]@{Name=$c.Name;CommandType=[string]$c.CommandType;Source=[string]$c.Source;Path=[string]$c.Path}|ConvertTo-Json -Compress}"
            )
            try:
                cp = subprocess.run(
                    [ps, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
                    capture_output=True,
                    text=True,
                    timeout=8,
                    errors="replace",
                )
                payload = cp.stdout.strip()
                if payload:
                    import json

                    result["powershell"] = json.loads(payload)
                    result["found"] = True
            except Exception:
                pass
    return result


def _path_executables(query: str, limit: int) -> list[dict[str, str]]:
    needle = query.casefold().strip()
    windows = os.name == "nt"
    pathext = {x.casefold() for x in os.getenv("PATHEXT", ".COM;.EXE;.BAT;.CMD;.PS1").split(";") if x}
    seen: set[str] = set()
    rows: list[dict[str, str]] = []

    for raw_dir in os.getenv("PATH", "").split(os.pathsep):
        raw_dir = raw_dir.strip('" ')
        if not raw_dir:
            continue
        directory = Path(raw_dir).expanduser()
        try:
            entries = directory.iterdir()
        except (OSError, PermissionError):
            continue
        try:
            for entry in entries:
                try:
                    if not entry.is_file():
                        continue
                except OSError:
                    continue
                suffix = entry.suffix.casefold()
                if windows and suffix not in pathext:
                    continue
                if not windows and not os.access(entry, os.X_OK):
                    continue
                display = entry.stem if windows and suffix in pathext else entry.name
                key = display.casefold()
                if key in seen or (needle and needle not in key and needle not in entry.name.casefold()):
                    continue
                seen.add(key)
                rows.append({"name": display, "path": str(entry), "source": "PATH"})
                if len(rows) >= limit:
                    return rows
        except OSError:
            continue
    rows.sort(key=lambda row: row["name"].casefold())
    return rows[:limit]


def _powershell_commands(query: str, limit: int) -> list[dict[str, str]]:
    if os.name != "nt" or limit <= 0:
        return []
    ps = shutil.which("powershell") or shutil.which("powershell.exe") or shutil.which("pwsh")
    if not ps:
        return []
    pattern = ("*" + str(query).replace("'", "''") + "*") if query else "*"
    script = (
        f"Get-Command -Name '{pattern}' -ErrorAction SilentlyContinue | "
        "Where-Object {$_.CommandType -in @('Application','Alias','Function','Cmdlet','ExternalScript')} | "
        f"Select-Object -First {int(limit)} Name,CommandType,Source,Path | ConvertTo-Json -Compress"
    )
    try:
        cp = subprocess.run(
            [ps, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
            errors="replace",
        )
        payload = cp.stdout.strip()
        if not payload:
            return []
        import json

        data = json.loads(payload)
        if isinstance(data, dict):
            data = [data]
        rows = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "name": str(item.get("Name") or ""),
                    "command_type": str(item.get("CommandType") or ""),
                    "source": str(item.get("Source") or "PowerShell"),
                    "path": str(item.get("Path") or ""),
                }
            )
        return rows
    except Exception:
        return []


def terminal_discover(query: str = "", limit: int = 80, include_powershell: bool = True) -> dict[str, Any]:
    limit = max(1, min(int(limit), 250))
    query = str(query or "").strip()
    path_rows = _path_executables(query, limit)
    remaining = max(0, limit - len(path_rows))
    ps_rows = _powershell_commands(query, remaining) if include_powershell else []

    combined: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in [*path_rows, *ps_rows]:
        key = (row.get("name", "").casefold(), row.get("command_type", "application").casefold())
        if key in seen:
            continue
        seen.add(key)
        combined.append(row)
        if len(combined) >= limit:
            break
    return {
        "query": query,
        "count": len(combined),
        "commands": combined,
        "unrestricted_by_name": True,
        "note": "IRAS may invoke any installed CLI/cmdlet; execution is still permission-gated and audited.",
    }


def terminal_capabilities() -> dict[str, Any]:
    shells = {}
    for name in ("powershell", "pwsh", "cmd", "bash", "sh"):
        path = shutil.which(name)
        if path:
            shells[name] = path
    return {
        "platform": os.name,
        "cwd": os.getcwd(),
        "shells": shells,
        "path_entries": [item for item in os.getenv("PATH", "").split(os.pathsep) if item],
        "pathext": os.getenv("PATHEXT", "") if os.name == "nt" else "",
        "unrestricted_by_cli_name": True,
        "supports_background_sessions": True,
        "supports_stdin": True,
        "permission_model": "SYSTEM_ACTION by default; destructive commands are promoted to CRITICAL; Master Control may authorize a bounded full session.",
    }


class _TerminalSession:
    def __init__(self, session_id: str, process: subprocess.Popen[str], command: str, cwd: str, shell: str):
        self.session_id = session_id
        self.process = process
        self.command = command
        self.cwd = cwd
        self.shell = shell
        self.created_at = time.time()
        self.updated_at = self.created_at
        self.stdout: queue.Queue[str] = queue.Queue()
        self.stderr: queue.Queue[str] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._start_reader(process.stdout, self.stdout)
        self._start_reader(process.stderr, self.stderr)

    def _start_reader(self, stream, target: queue.Queue[str]) -> None:
        if stream is None:
            return

        def reader():
            try:
                for line in iter(stream.readline, ""):
                    target.put(line)
                    self.updated_at = time.time()
            except Exception as exc:
                target.put(f"<reader error: {type(exc).__name__}: {exc}>\n")
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        thread = threading.Thread(target=reader, daemon=True)
        self._threads.append(thread)
        thread.start()

    @staticmethod
    def _drain(source: queue.Queue[str], limit: int = 50000) -> str:
        chunks: list[str] = []
        size = 0
        while size < limit:
            try:
                item = source.get_nowait()
            except queue.Empty:
                break
            chunks.append(item)
            size += len(item)
        return _truncate("".join(chunks))

    def snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "command": self.command,
            "cwd": self.cwd,
            "shell": self.shell,
            "running": self.process.poll() is None,
            "returncode": self.process.poll(),
            "pid": int(self.process.pid),
            "stdout": self._drain(self.stdout),
            "stderr": self._drain(self.stderr),
            "age_seconds": round(max(0.0, time.time() - self.created_at), 3),
        }


class TerminalSessionManager:
    def __init__(self, max_sessions: int = 32):
        self._sessions: dict[str, _TerminalSession] = {}
        self._lock = threading.RLock()
        self._max_sessions = max(4, min(int(max_sessions), 128))

    def _prune_completed(self) -> None:
        # Keep a bounded amount of session history. Running sessions are never
        # evicted; completed sessions are dropped oldest-first when necessary.
        completed = sorted(
            (s for s in self._sessions.values() if s.process.poll() is not None),
            key=lambda s: s.updated_at,
        )
        while len(self._sessions) >= self._max_sessions and completed:
            stale = completed.pop(0)
            self._sessions.pop(stale.session_id, None)

    def start(
        self,
        command: str,
        cwd: str | None = None,
        shell: str = "auto",
        env: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        command = str(command or "").strip()
        if not command:
            raise ValueError("command is required")
        workdir = str(Path(cwd).expanduser()) if cwd else os.getcwd()
        argv, use_shell, resolved_shell = _prepare_command(command, shell)
        process = subprocess.Popen(
            argv,
            cwd=workdir,
            shell=use_shell,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            errors="replace",
            env=_merge_env(env),
        )
        session_id = uuid.uuid4().hex[:12]
        session = _TerminalSession(session_id, process, command, workdir, resolved_shell)
        with self._lock:
            self._prune_completed()
            if len(self._sessions) >= self._max_sessions:
                process.terminate()
                raise RuntimeError(
                    f"Terminal session limit ({self._max_sessions}) reached; stop an active session before starting another."
                )
            self._sessions[session_id] = session
        return session.snapshot()

    def get(self, session_id: str) -> _TerminalSession:
        key = str(session_id or "").strip()
        with self._lock:
            session = self._sessions.get(key)
        if not session:
            raise KeyError(f"Unknown terminal session: {key}")
        return session

    def read(self, session_id: str) -> dict[str, Any]:
        return self.get(session_id).snapshot()

    def send(self, session_id: str, text: str, newline: bool = True) -> dict[str, Any]:
        session = self.get(session_id)
        if session.process.poll() is not None:
            return session.snapshot()
        if session.process.stdin is None:
            raise RuntimeError("Terminal session stdin is unavailable.")
        payload = str(text or "") + ("\n" if newline else "")
        session.process.stdin.write(payload)
        session.process.stdin.flush()
        session.updated_at = time.time()
        time.sleep(0.05)
        return session.snapshot()

    def stop(self, session_id: str, force: bool = False) -> dict[str, Any]:
        session = self.get(session_id)
        if session.process.poll() is None:
            if force:
                session.process.kill()
            else:
                session.process.terminate()
            try:
                session.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                session.process.kill()
                session.process.wait(timeout=5)
        return session.snapshot()

    def list(self) -> dict[str, Any]:
        with self._lock:
            sessions = list(self._sessions.values())
        return {
            "count": len(sessions),
            "sessions": [
                {
                    "session_id": s.session_id,
                    "command": s.command,
                    "cwd": s.cwd,
                    "shell": s.shell,
                    "running": s.process.poll() is None,
                    "returncode": s.process.poll(),
                    "pid": int(s.process.pid),
                }
                for s in sessions
            ],
        }


_SESSIONS = TerminalSessionManager()


def terminal_start(command: str, cwd: str | None = None, shell: str = "auto", env: dict[str, Any] | None = None):
    return _SESSIONS.start(command, cwd=cwd, shell=shell, env=env)


def terminal_read(session_id: str):
    return _SESSIONS.read(session_id)


def terminal_send(session_id: str, text: str, newline: bool = True):
    return _SESSIONS.send(session_id, text, newline=newline)


def terminal_stop(session_id: str, force: bool = False):
    return _SESSIONS.stop(session_id, force=force)


def terminal_sessions():
    return _SESSIONS.list()


TOOLS = [
    Tool(
        "terminal_capabilities",
        "Inspect the authorized computer's universal terminal capabilities. IRAS terminal execution is not restricted to a predefined CLI list.",
        {"type": "object", "properties": {}},
        terminal_capabilities,
        PermissionLevel.READ,
    ),
    Tool(
        "terminal_discover",
        "Discover installed CLI programs, PowerShell cmdlets/functions/aliases, and PATH commands dynamically. Use this before assuming a CLI is unavailable.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 250},
                "include_powershell": {"type": "boolean"},
            },
        },
        terminal_discover,
        PermissionLevel.READ,
    ),
    Tool(
        "terminal_which",
        "Resolve any CLI/PowerShell command by name on the authorized computer without a hard-coded allowlist.",
        {"type": "object", "properties": {"name": {"type": "string", "minLength": 1}}, "required": ["name"]},
        terminal_which,
        PermissionLevel.READ,
    ),
    Tool(
        "terminal_exec",
        "Run any installed CLI tool or shell command on the authorized computer. Supports PowerShell/cmd/pwsh/bash/sh/direct execution, cwd, stdin, environment overrides, and bounded timeouts. Execution is permission-gated and audited; destructive commands are CRITICAL.",
        {
            "type": "object",
            "properties": {
                "command": {"type": "string", "minLength": 1},
                "cwd": {"type": "string"},
                "timeout": {"type": "integer", "minimum": 1, "maximum": 3600},
                "shell": {"type": "string", "enum": ["auto", "powershell", "pwsh", "cmd", "bash", "sh", "direct"]},
                "stdin": {"type": "string"},
                "env": {"type": "object"},
            },
            "required": ["command"],
        },
        terminal_exec,
        PermissionLevel.SYSTEM_ACTION,
        classify_terminal,
    ),
    Tool(
        "terminal_start",
        "Start any installed CLI command as a persistent terminal session so IRAS can read output and send stdin later. No CLI-name allowlist is used.",
        {
            "type": "object",
            "properties": {
                "command": {"type": "string", "minLength": 1},
                "cwd": {"type": "string"},
                "shell": {"type": "string", "enum": ["auto", "powershell", "pwsh", "cmd", "bash", "sh", "direct"]},
                "env": {"type": "object"},
            },
            "required": ["command"],
        },
        terminal_start,
        PermissionLevel.SYSTEM_ACTION,
        classify_terminal,
    ),
    Tool(
        "terminal_read",
        "Read new stdout/stderr and status from a persistent terminal session.",
        {"type": "object", "properties": {"session_id": {"type": "string", "minLength": 1}}, "required": ["session_id"]},
        terminal_read,
        PermissionLevel.READ,
    ),
    Tool(
        "terminal_send",
        "Send stdin to a running terminal session. This can answer prompts or interact with any CLI and remains permission-gated.",
        {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1},
                "text": {"type": "string"},
                "newline": {"type": "boolean"},
            },
            "required": ["session_id", "text"],
        },
        terminal_send,
        PermissionLevel.SYSTEM_ACTION,
    ),
    Tool(
        "terminal_stop",
        "Stop a persistent terminal session started by IRAS.",
        {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "minLength": 1},
                "force": {"type": "boolean"},
            },
            "required": ["session_id"],
        },
        terminal_stop,
        PermissionLevel.SYSTEM_ACTION,
    ),
    Tool(
        "terminal_sessions",
        "List terminal sessions IRAS has started and their current process state.",
        {"type": "object", "properties": {}},
        terminal_sessions,
        PermissionLevel.READ,
    ),
]
