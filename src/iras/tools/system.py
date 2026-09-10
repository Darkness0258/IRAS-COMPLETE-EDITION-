from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from iras.models import PermissionLevel
from iras.tools.base import Tool


def system_info():
    return {
        'os': platform.platform(),
        'machine': platform.machine(),
        'processor': platform.processor(),
        'python': platform.python_version(),
        'hostname': platform.node(),
        'user': os.getenv('USERNAME') or os.getenv('USER'),
    }


def list_processes():
    if os.name == 'nt':
        cp = subprocess.run(
            ['tasklist', '/FO', 'CSV', '/NH'],
            capture_output=True,
            text=True,
            errors='replace',
        )
        return cp.stdout[-30000:]
    cp = subprocess.run(
        ['ps', '-eo', 'pid,comm,%cpu,%mem'],
        capture_output=True,
        text=True,
        errors='replace',
    )
    return cp.stdout[-30000:]


def _windows_candidates(alias: str) -> list[Path]:
    local = Path(os.getenv('LOCALAPPDATA', ''))
    roaming = Path(os.getenv('APPDATA', ''))
    pf = Path(os.getenv('PROGRAMFILES', ''))
    pf86 = Path(os.getenv('PROGRAMFILES(X86)', ''))

    table = {
        'chrome': [
            local / 'Google/Chrome/Application/chrome.exe',
            pf / 'Google/Chrome/Application/chrome.exe',
            pf86 / 'Google/Chrome/Application/chrome.exe',
        ],
        'spotify': [
            roaming / 'Spotify/Spotify.exe',
            local / 'Microsoft/WindowsApps/Spotify.exe',
        ],
        'code': [
            local / 'Programs/Microsoft VS Code/Code.exe',
            pf / 'Microsoft VS Code/Code.exe',
        ],
        'vscode': [
            local / 'Programs/Microsoft VS Code/Code.exe',
            pf / 'Microsoft VS Code/Code.exe',
        ],
        'notepad': [Path(os.getenv('WINDIR', r'C:\Windows')) / 'System32/notepad.exe'],
        'explorer': [Path(os.getenv('WINDIR', r'C:\Windows')) / 'explorer.exe'],
    }
    return [p for p in table.get(alias, []) if str(p)]


def _canonical_alias(value: str) -> str:
    normalized = value.strip().strip('"').strip("'").lower()
    aliases = {
        'google chrome': 'chrome',
        'google-chrome': 'chrome',
        'chrome.exe': 'chrome',
        'spotify.exe': 'spotify',
        'visual studio code': 'code',
        'vs code': 'code',
        'code.exe': 'code',
        'notepad.exe': 'notepad',
        'explorer.exe': 'explorer',
        'file explorer': 'explorer',
    }
    return aliases.get(normalized, normalized)


def classify_launch(args: dict[str, Any]) -> PermissionLevel:
    command = str(args.get('command', '')).strip()
    lowered = command.lower()
    # launch_app must never become a back door around run_shell.
    interpreters = ('cmd', 'cmd.exe', 'powershell', 'powershell.exe', 'pwsh', 'bash', 'sh', 'wsl', 'python', 'python.exe')
    if any(ch in command for ch in ('\n', '\r', '&', '|', '>', '<', '^')):
        return PermissionLevel.SYSTEM_ACTION
    first = lowered.split(maxsplit=1)[0].strip('"\'') if lowered else ''
    if first in interpreters:
        return PermissionLevel.SYSTEM_ACTION
    # Plain application names/paths are safe; command lines with arguments are elevated.
    try:
        parts = shlex.split(command, posix=False)
    except ValueError:
        return PermissionLevel.SYSTEM_ACTION
    return PermissionLevel.SAFE_ACTION if len(parts) <= 1 else PermissionLevel.SYSTEM_ACTION


def launch_app(command: str):
    """Launch an application without invoking a shell.

    Common Windows app names are resolved explicitly. Unknown commands must be
    installed executables discoverable on PATH. Shell metacharacters are rejected.
    """
    command = (command or '').strip()
    if not command:
        raise ValueError('Application name is empty.')
    if any(ch in command for ch in ('\n', '\r', '&', '|', '>', '<', '^')):
        raise PermissionError('Shell operators are not allowed in launch_app; use run_shell with approval instead.')

    # Resolve a single app name first. This covers natural model outputs such as
    # "google-chrome" on Windows without pretending a failed shell command worked.
    alias = _canonical_alias(command)

    if os.name == 'nt':
        if alias == 'spotify':
            for candidate in _windows_candidates(alias):
                if candidate.exists():
                    proc = subprocess.Popen([str(candidate)], shell=False)
                    return {'launched': str(candidate), 'pid': proc.pid, 'app': 'spotify'}
            # Store/MSIX Spotify normally registers the spotify: protocol.
            try:
                os.startfile('spotify:')  # type: ignore[attr-defined]
                return {'launched': 'spotify:', 'app': 'spotify'}
            except OSError as exc:
                raise FileNotFoundError('Spotify is not installed or its protocol is not registered.') from exc

        for candidate in _windows_candidates(alias):
            if candidate.exists():
                proc = subprocess.Popen([str(candidate)], shell=False)
                time.sleep(0.15)
                rc = proc.poll()
                if rc not in (None, 0):
                    raise RuntimeError(f'{candidate.name} exited immediately with code {rc}.')
                return {'launched': str(candidate), 'pid': proc.pid, 'app': alias}

    # For cross-platform apps, accept a real executable on PATH. No shell is used.
    executable = shutil.which(command) or shutil.which(alias)
    if executable:
        proc = subprocess.Popen([executable], shell=False)
        time.sleep(0.15)
        rc = proc.poll()
        if rc not in (None, 0):
            raise RuntimeError(f'{Path(executable).name} exited immediately with code {rc}.')
        return {'launched': executable, 'pid': proc.pid, 'app': alias}

    # Explicit existing executable/file path.
    p = Path(command.strip('"')).expanduser()
    if p.exists():
        proc = subprocess.Popen([str(p.resolve())], shell=False)
        return {'launched': str(p.resolve()), 'pid': proc.pid}

    raise FileNotFoundError(
        f"Application '{command}' was not found. Use an installed app name or an explicit executable path."
    )


def kill_process(pid):
    pid = int(pid)
    if os.name == 'nt':
        cp = subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True, text=True)
    else:
        cp = subprocess.run(['kill', '-TERM', str(pid)], capture_output=True, text=True)
    return {'returncode': cp.returncode, 'stdout': cp.stdout, 'stderr': cp.stderr}


def screenshot(path=None):
    from PIL import ImageGrab
    if path is None:
        path = str(Path('screenshots') / 'screen.png')
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(all_screens=True).save(p)
    return str(p)


TOOLS = [
    Tool('system_info', 'Get basic local system information.', {'type': 'object', 'properties': {}}, system_info, PermissionLevel.READ),
    Tool('list_processes', 'List processes running on the local computer.', {'type': 'object', 'properties': {}}, list_processes, PermissionLevel.READ),
    Tool(
        'launch_app',
        'Launch an installed desktop application by simple app name or executable path. Do not use shell commands here.',
        {'type': 'object', 'properties': {'command': {'type': 'string'}}, 'required': ['command']},
        launch_app,
        PermissionLevel.SAFE_ACTION,
        classify_launch,
    ),
    Tool('kill_process', 'Terminate a process by PID.', {'type': 'object', 'properties': {'pid': {'type': 'integer'}}, 'required': ['pid']}, kill_process, PermissionLevel.SYSTEM_ACTION),
    Tool('capture_screen', 'Capture the current desktop screenshot to a file.', {'type': 'object', 'properties': {'path': {'type': 'string'}}}, screenshot, PermissionLevel.READ),
]
