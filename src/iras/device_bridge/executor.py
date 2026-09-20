from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import platform
from pathlib import Path
import shutil
import tempfile
import fnmatch
import re
import subprocess
import sys
import time
from urllib.parse import urlparse
import webbrowser

import httpx

from iras.tools.system import (
    launch_app,
    system_info,
)
from iras.device_bridge.universal_control import (
    UniversalWindowsController,
)
from iras.device_bridge.visual_control import (
    SemanticVisualController,
)
from iras.device_bridge.computer_use import (
    UniversalComputerController,
)
from iras.device_bridge.whatsapp_workflow import (
    open_chat_and_verify as open_whatsapp_chat_and_verify,
)
from iras.device_bridge.primitives import VerifiedUIPrimitives
from iras.device_bridge.verifiers import SemanticVerifier
from iras.remote_access import is_sensitive_path
from iras.safety_runtime import EmergencyStop
from iras.device_bridge.software_install import (
    manager_status as software_manager_status_impl,
    search as software_search_impl,
    show as software_show_impl,
    list_installed as software_list_impl,
    available_upgrades as software_upgrades_impl,
    install as software_install_impl,
    upgrade as software_upgrade_impl,
    uninstall as software_uninstall_impl,
    prepare_url as software_prepare_url_impl,
    install_prepared as software_install_prepared_impl,
)


DEFAULT_CAPABILITIES = [
    "system_info",
    "detect_apps",
    "app_control",
    "open_app",
    "open_url",
    "open_project",
    "list_directory",
    "read_text",
    "read_text_range",
    "search_text",
    "file_info",
    "find_projects",
    "git_status",
    "git_diff",
    "git_log",
    "git_head",
    "git_restore_checkpoint",
    "run_tests",
    "local_llm_complete",
    "local_llm_status",
    "capture_screen",
    "interact_app",
    "observe_ui",
    "semantic_action",
    "computer_status",
    "computer_observe",
    "computer_action",
    "computer_verify",
    "whatsapp_open_chat",
    "spotify_search",
    "spotify_play",
    "media_control",
    "screen_preview",
    "list_processes",
    "kill_process",
    "write_text",
    "replace_text",
    "make_directory",
    "copy_path",
    "move_path",
    "delete_path",
    "clipboard_get",
    "clipboard_set",
    "ui_find_text",
    "ui_click_text",
    "ui_type_text",
    "ui_wait_text",
    "ui_scroll_until_text",
    "verify_state",
    "power_action",
    "software_manager_status",
    "software_search",
    "software_show",
    "software_list",
    "software_upgrades",
    "software_install",
    "software_upgrade",
    "software_uninstall",
    "software_prepare_url",
    "software_install_prepared",
    "run_command",
]


class DeviceExecutor:
    """Strict, non-shell executor for commands arriving from IRAS Cloud."""

    APP_ALIASES = {
        "chrome",
        "google chrome",
        "spotify",
        "code",
        "vscode",
        "visual studio code",
        "notepad",
        "explorer",
        "file explorer",
    }

    def __init__(
        self,
        allowed_roots: list[str] | None = None,
    ):
        roots = (
            allowed_roots
            if allowed_roots is not None
            else self.default_roots()
        )

        self.allowed_roots = []

        for root in roots:
            try:
                path = (
                    Path(root)
                    .expanduser()
                    .resolve()
                )
            except Exception:
                continue

            if (
                path.exists()
                and path
                not in self.allowed_roots
            ):
                self.allowed_roots.append(
                    path
                )

        if not self.allowed_roots:
            self.allowed_roots = [
                Path.home().resolve()
            ]

        self.ui = UniversalWindowsController()
        self.visual = SemanticVisualController(
            self.ui
        )
        self.computer = UniversalComputerController(
            self.ui,
            self.visual,
        )
        self.primitives = VerifiedUIPrimitives(self.ui, self.computer)
        self.verifier = SemanticVerifier(self)
        self.emergency_stop = EmergencyStop()

    @staticmethod
    def default_roots() -> list[str]:
        values = [
            str(Path.home()),
        ]

        raw = os.getenv(
            "IRAS_BRIDGE_ROOTS",
            "",
        ).strip()

        if raw:
            values.extend(
                item.strip()
                for item in raw.split(
                    os.pathsep
                )
                if item.strip()
            )

        for candidate in (
            Path("D:/Projects"),
            Path("C:/workstation/Projects"),
        ):
            if candidate.exists():
                values.append(
                    str(candidate)
                )

        return values

    def _path(
        self,
        value: str,
        *,
        must_exist: bool = True,
    ) -> Path:
        path = (
            Path(value)
            .expanduser()
            .resolve()
        )

        allowed = False

        for root in self.allowed_roots:
            try:
                path.relative_to(root)
                allowed = True
                break
            except ValueError:
                pass

        if not allowed:
            raise PermissionError(
                "Remote path is outside IRAS_BRIDGE_ROOTS."
            )

        if (
            must_exist
            and not path.exists()
        ):
            raise FileNotFoundError(
                path
            )

        return path

    def execute(
        self,
        action: str,
        arguments: dict,
    ):
        arguments = dict(
            arguments
            or {}
        )
        self.emergency_stop.assert_clear()

        handlers = {
            "system_info": self.system_info,
            "detect_apps": self.detect_apps,
            "app_control": self.app_control,
            "open_app": self.open_app,
            "open_url": self.open_url,
            "open_project": self.open_project,
            "list_directory": self.list_directory,
            "read_text": self.read_text,
            "read_text_range": self.read_text_range,
            "search_text": self.search_text,
            "file_info": self.file_info,
            "find_projects": self.find_projects,
            "git_status": self.git_status,
            "git_diff": self.git_diff,
            "git_log": self.git_log,
            "git_head": self.git_head,
            "git_restore_checkpoint": self.git_restore_checkpoint,
            "run_tests": self.run_tests,
            "local_llm_complete": self.local_llm_complete,
            "local_llm_status": self.local_llm_status,
            "capture_screen": self.capture_screen,
            "interact_app": self.interact_app,
            "observe_ui": self.observe_ui,
            "semantic_action": self.semantic_action,
            "computer_status": self.computer_status,
            "computer_observe": self.computer_observe,
            "computer_action": self.computer_action,
            "computer_verify": self.computer_verify,
            "whatsapp_open_chat": self.whatsapp_open_chat,
            "spotify_search": self.spotify_search,
            "spotify_play": self.spotify_play,
            "media_control": self.media_control,
            "screen_preview": self.screen_preview,
            "list_processes": self.list_processes,
            "kill_process": self.kill_process,
            "write_text": self.write_text,
            "replace_text": self.replace_text,
            "make_directory": self.make_directory,
            "copy_path": self.copy_path,
            "move_path": self.move_path,
            "delete_path": self.delete_path,
            "clipboard_get": self.clipboard_get,
            "clipboard_set": self.clipboard_set,
            "ui_find_text": self.ui_find_text,
            "ui_click_text": self.ui_click_text,
            "ui_type_text": self.ui_type_text,
            "ui_wait_text": self.ui_wait_text,
            "ui_scroll_until_text": self.ui_scroll_until_text,
            "verify_state": self.verify_state,
            "power_action": self.power_action,
            "software_manager_status": self.software_manager_status,
            "software_search": self.software_search,
            "software_show": self.software_show,
            "software_list": self.software_list,
            "software_upgrades": self.software_upgrades,
            "software_install": self.software_install,
            "software_upgrade": self.software_upgrade,
            "software_uninstall": self.software_uninstall,
            "software_prepare_url": self.software_prepare_url,
            "software_install_prepared": self.software_install_prepared,
            "run_command": self.run_command,
        }

        handler = handlers.get(
            str(action)
        )

        if handler is None:
            raise PermissionError(
                f"Remote action '{action}' is not allowed."
            )

        return handler(
            **arguments
        )

    def system_info(self):
        info = system_info()
        info["allowed_roots"] = [
            str(path)
            for path in self.allowed_roots
        ]
        return info

    def detect_apps(
        self,
        query: str = "",
        limit: int = 100,
    ):
        return {
            "installed": self.ui.catalog.list_apps(
                query=(query or None),
                limit=limit,
            ),
            "running": self.ui.detect_running_apps(
                query=(query or None),
                limit=limit,
            ),
        }

    def app_control(
        self,
        app: str,
        action: str,
    ):
        return self.ui.app_control(
            app,
            action,
        )

    def open_app(
        self,
        app: str,
    ):
        return self.ui.catalog.launch(
            app
        )

    def open_url(
        self,
        url: str,
    ):
        parsed = urlparse(
            str(url)
        )

        if parsed.scheme not in {
            "http",
            "https",
        } or not parsed.netloc:
            raise ValueError(
                "Only http/https URLs are allowed."
            )

        opened = webbrowser.open(
            url,
            new=2,
        )

        return {
            "opened": bool(opened),
            "url": url,
        }

    def _code_executable(self) -> str:
        candidates = [
            shutil.which("code"),
            shutil.which("code.cmd"),
            shutil.which("code.exe"),
        ]

        local = Path(
            os.getenv(
                "LOCALAPPDATA",
                "",
            )
        )

        candidates.extend(
            [
                str(
                    local
                    / "Programs"
                    / "Microsoft VS Code"
                    / "Code.exe"
                ),
                r"C:\Program Files\Microsoft VS Code\Code.exe",
            ]
        )

        for candidate in candidates:
            if (
                candidate
                and Path(
                    candidate
                ).exists()
            ):
                return str(
                    Path(candidate)
                )

        raise FileNotFoundError(
            "VS Code is not installed or could not be found."
        )

    def open_project(
        self,
        path: str,
    ):
        project = self._path(
            path
        )

        if not project.is_dir():
            raise NotADirectoryError(
                project
            )

        executable = (
            self._code_executable()
        )

        process = subprocess.Popen(
            [
                executable,
                str(project),
            ],
            shell=False,
        )

        return {
            "opened": str(project),
            "app": "vscode",
            "pid": process.pid,
        }

    def list_directory(
        self,
        path: str,
        include_hidden: bool = False,
    ):
        directory = self._path(
            path
        )

        if not directory.is_dir():
            raise NotADirectoryError(
                directory
            )

        output = []

        for item in sorted(
            directory.iterdir(),
            key=lambda value: (
                value.name.lower()
            ),
        ):
            if (
                not include_hidden
                and item.name.startswith(
                    "."
                )
            ):
                continue

            is_link = item.is_symlink()
            item_type = "symlink" if is_link else ("dir" if item.is_dir() else "file")
            size = None
            if not is_link and item.is_file():
                try:
                    size = item.stat().st_size
                except OSError:
                    size = None
            output.append(
                {
                    "name": item.name,
                    "type": item_type,
                    "size": size,
                }
            )

            if len(output) >= 300:
                break

        return {
            "path": str(directory),
            "items": output,
        }

    def read_text(
        self,
        path: str,
        max_chars: int = 12000,
    ):
        file_path = self._path(
            path
        )

        if not file_path.is_file():
            raise FileNotFoundError(
                file_path
            )

        max_chars = max(
            1,
            min(
                int(max_chars),
                20000,
            ),
        )

        return {
            "path": str(file_path),
            "content": (
                file_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )[:max_chars]
            ),
        }

    def read_text_range(
        self,
        path: str,
        start_line: int = 1,
        end_line: int = 200,
    ):
        file_path = self._path(path)
        if not file_path.is_file():
            raise FileNotFoundError(file_path)
        if file_path.stat().st_size > 5_000_000:
            raise ValueError("read_text_range refuses files larger than 5 MB.")
        start_line = max(1, int(start_line))
        end_line = max(start_line, min(int(end_line), start_line + 999))
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        selected = lines[start_line - 1:end_line]
        return {
            "path": str(file_path),
            "start_line": start_line,
            "end_line": min(end_line, len(lines)),
            "total_lines": len(lines),
            "content": "\n".join(selected),
        }

    def search_text(
        self,
        root: str,
        query: str,
        pattern: str = "*",
        regex: bool = False,
        case_sensitive: bool = False,
        max_matches: int = 120,
        max_files: int = 600,
    ):
        directory = self._path(root)
        if not directory.is_dir():
            raise NotADirectoryError(directory)
        query = str(query or "")
        if not query:
            raise ValueError("query is required.")
        if len(query) > 1000:
            raise ValueError("query is too long.")
        pattern = str(pattern or "*")[:200]
        max_matches = max(1, min(int(max_matches), 500))
        max_files = max(1, min(int(max_files), 3000))
        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = re.compile(query, flags) if regex else None
        needle = query if case_sensitive else query.lower()
        matches = []
        scanned = 0
        skipped_symlinks = 0
        for candidate in directory.rglob("*"):
            if scanned >= max_files or len(matches) >= max_matches:
                break
            try:
                if candidate.is_symlink():
                    skipped_symlinks += 1
                    continue
                if is_sensitive_path(candidate):
                    continue
                if not candidate.is_file() or not fnmatch.fnmatch(candidate.name, pattern):
                    continue
                if candidate.stat().st_size > 2_000_000:
                    continue
            except OSError:
                continue
            scanned += 1
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                found = bool(compiled.search(line)) if compiled else (needle in (line if case_sensitive else line.lower()))
                if found:
                    matches.append({
                        "path": str(candidate),
                        "relative_path": str(candidate.relative_to(directory)),
                        "line": line_no,
                        "text": line[:1200],
                    })
                    if len(matches) >= max_matches:
                        break
        return {
            "root": str(directory),
            "query": query,
            "pattern": pattern,
            "matches": matches,
            "match_count": len(matches),
            "files_scanned": scanned,
            "symlinks_skipped": skipped_symlinks,
            "truncated": scanned >= max_files or len(matches) >= max_matches,
        }

    def file_info(self, path: str, sha256: bool = True):
        target = self._path(path)
        stat = target.stat()
        result = {
            "path": str(target),
            "type": "dir" if target.is_dir() else "file",
            "size": stat.st_size if target.is_file() else None,
            "modified": stat.st_mtime,
            "is_symlink": target.is_symlink(),
        }
        if sha256 and target.is_file():
            if stat.st_size > 100_000_000:
                raise ValueError("file_info hashing is limited to files <= 100 MB.")
            digest = hashlib.sha256()
            with target.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            result["sha256"] = digest.hexdigest()
        return result

    def find_projects(
        self,
        query: str = "",
        max_depth: int = 3,
        max_results: int = 20,
    ):
        """Discover likely development projects inside configured bridge roots.

        Discovery is read-only, bounded, never follows symlinks, and allocates
        scanning budget fairly across every allowed root. A large first root
        therefore cannot starve later roots such as ``D:\\Projects``. When a
        query is supplied, only identity-matching projects are returned; IRAS
        must never silently substitute an unrelated repository.
        """
        query = str(query or "").strip().lower()
        max_depth = max(0, min(int(max_depth), 5))
        max_results = max(1, min(int(max_results), 50))
        markers = (
            ".git",
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "requirements.txt",
        )
        results = []
        seen: set[str] = set()
        total_scanned = 0
        roots = []
        for raw_root in self.allowed_roots:
            try:
                roots.append(raw_root.resolve())
            except OSError:
                continue

        # Keep discovery bounded while guaranteeing every configured root a fair
        # share. Previously one large C:\Users tree could consume the global
        # budget before D:\Projects was examined.
        max_scanned_total = 3000
        per_root_budget = max(250, max_scanned_total // max(1, len(roots)))
        root_scan_counts: dict[str, int] = {}
        truncated_by_budget = False

        def consider(candidate: Path, depth: int) -> None:
            try:
                if candidate.is_symlink() or not candidate.is_dir():
                    return
                resolved = candidate.resolve()
            except OSError:
                return
            key = os.path.normcase(str(resolved))
            if key in seen:
                return
            seen.add(key)
            present = []
            for marker_name in markers:
                try:
                    if (resolved / marker_name).exists():
                        present.append(marker_name)
                except OSError:
                    pass
            if not present:
                return
            haystack = (resolved.name + " " + str(resolved)).lower()
            query_match = bool(query and query in haystack)
            git_repo = ".git" in present
            score = (100 if query_match else 0) + (40 if git_repo else 0) + max(0, 12 - depth)
            results.append({
                "path": str(resolved),
                "name": resolved.name,
                "depth": depth,
                "markers": present,
                "git": git_repo,
                "query_match": query_match,
                "score": score,
            })

        for root in roots:
            queue: list[tuple[Path, int]] = [(root, 0)]
            scanned_this_root = 0
            while queue and scanned_this_root < per_root_budget:
                current, depth = queue.pop(0)
                scanned_this_root += 1
                total_scanned += 1
                consider(current, depth)
                if depth >= max_depth:
                    continue
                try:
                    children = list(current.iterdir())
                except OSError:
                    continue
                # Query-looking directories first, then stable alphabetical
                # traversal. This makes named project lookup fast without
                # weakening the bounded scan.
                children.sort(
                    key=lambda item: (
                        0 if query and query in item.name.lower() else 1,
                        item.name.lower(),
                    )
                )
                for child in children:
                    if child.name in {
                        ".git", ".venv", "venv", "node_modules", "__pycache__",
                        ".pytest_cache", ".mypy_cache", ".ruff_cache",
                    }:
                        continue
                    try:
                        if child.is_symlink() or not child.is_dir():
                            continue
                    except OSError:
                        continue
                    queue.append((child, depth + 1))
            root_scan_counts[str(root)] = scanned_this_root
            if queue:
                truncated_by_budget = True

        results.sort(key=lambda item: (-int(item["score"]), str(item["path"]).lower()))
        if query:
            # Fail closed for named-project discovery. Returning an unrelated
            # repository here caused autonomous engineering to operate on the
            # wrong checkout during RC6 real-device testing.
            results = [item for item in results if item["query_match"]]

        return {
            "query": query,
            "allowed_roots": [str(path) for path in roots],
            "projects": results[:max_results],
            "project_count": min(len(results), max_results),
            "scanned_directories": total_scanned,
            "scanned_by_root": root_scan_counts,
            "truncated": truncated_by_budget or len(results) > max_results,
        }

    def git_status(
        self,
        repo: str,
    ):
        repository = self._path(
            repo
        )

        if not repository.is_dir():
            raise NotADirectoryError(
                repository
            )

        result = subprocess.run(
            [
                "git",
                "status",
                "--short",
                "--branch",
            ],
            cwd=repository,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=45,
            shell=False,
        )

        return {
            "repo": str(repository),
            "returncode": (
                result.returncode
            ),
            "stdout": (
                result.stdout[-20000:]
            ),
            "stderr": (
                result.stderr[-8000:]
            ),
        }

    def git_diff(self, repo: str, path: str = "", staged: bool = False, max_chars: int = 30000):
        repository = self._path(repo)
        if not repository.is_dir():
            raise NotADirectoryError(repository)
        command = ["git", "diff", "--no-ext-diff"]
        if staged:
            command.append("--cached")
        if path:
            candidate = (repository / str(path)).resolve()
            try:
                relative = candidate.relative_to(repository)
            except ValueError as exc:
                raise PermissionError("git_diff path must stay inside the repository.") from exc
            command.extend(["--", str(relative)])
        result = subprocess.run(command, cwd=repository, capture_output=True, text=True, errors="replace", timeout=45, shell=False)
        max_chars = max(1000, min(int(max_chars), 100000))
        return {
            "repo": str(repository),
            "returncode": result.returncode,
            "stdout": result.stdout[:max_chars],
            "stderr": result.stderr[-8000:],
            "truncated": len(result.stdout) > max_chars,
        }

    def git_log(self, repo: str, limit: int = 20):
        repository = self._path(repo)
        if not repository.is_dir():
            raise NotADirectoryError(repository)
        limit = max(1, min(int(limit), 100))
        result = subprocess.run(
            ["git", "log", f"-{limit}", "--oneline", "--decorate", "--no-color"],
            cwd=repository,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=45,
            shell=False,
        )
        return {"repo": str(repository), "returncode": result.returncode, "stdout": result.stdout[-30000:], "stderr": result.stderr[-8000:]}

    def git_head(self, repo: str):
        repository = self._path(repo)
        if not repository.is_dir():
            raise NotADirectoryError(repository)
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
            shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Unable to resolve repository HEAD: " + result.stderr[-1000:])
        head = result.stdout.strip()
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", head):
            raise RuntimeError("Repository HEAD was not a full commit hash.")
        return {"repo": str(repository), "head": head.lower()}

    def git_restore_checkpoint(self, repo: str, head: str, baseline_clean: bool = False):
        """Safely restore tracked working-tree changes to a verified checkpoint.

        This deliberately refuses to reset commits or delete untracked files.
        Rollback is allowed only when the job started from a clean tree and the
        repository HEAD has not changed since the checkpoint was captured.
        """
        repository = self._path(repo)
        if not repository.is_dir():
            raise NotADirectoryError(repository)
        if not bool(baseline_clean):
            raise PermissionError("Rollback is unavailable because the job did not start from a clean Git working tree.")
        checkpoint = str(head or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40,64}", checkpoint):
            raise ValueError("Rollback checkpoint must be a full Git commit hash.")
        current = self.git_head(str(repository))["head"]
        if current != checkpoint:
            raise PermissionError(
                "Rollback refused because repository HEAD changed after the checkpoint. "
                "IRAS will not reset or rewrite commits automatically."
            )
        before = subprocess.run(
            ["git", "status", "--porcelain=v1"],
            cwd=repository, capture_output=True, text=True, errors="replace", timeout=30, shell=False,
        )
        restore = subprocess.run(
            ["git", "restore", "--source", checkpoint, "--staged", "--worktree", "--", "."],
            cwd=repository, capture_output=True, text=True, errors="replace", timeout=90, shell=False,
        )
        if restore.returncode != 0:
            raise RuntimeError("Git rollback failed: " + restore.stderr[-2000:])
        after = subprocess.run(
            ["git", "status", "--porcelain=v1"],
            cwd=repository, capture_output=True, text=True, errors="replace", timeout=30, shell=False,
        )
        remaining = [line for line in after.stdout.splitlines() if line.strip()]
        untracked = [line[3:] for line in remaining if line.startswith("?? ")]
        tracked_remaining = [line for line in remaining if not line.startswith("?? ")]
        return {
            "repo": str(repository),
            "head": current,
            "restored": not tracked_remaining,
            "tracked_changes_before": [line for line in before.stdout.splitlines() if line and not line.startswith("?? ")][:200],
            "tracked_changes_remaining": tracked_remaining[:200],
            "untracked_preserved": untracked[:200],
            "note": "IRAS restores tracked changes only; untracked files are intentionally preserved.",
        }

    def local_llm_status(self):
        """Return bounded loopback Ollama readiness without running inference."""
        raw_base = os.getenv(
            "IRAS_DEVICE_OLLAMA_BASE_URL",
            "http://127.0.0.1:11434/v1",
        ).strip().rstrip("/")
        parsed = urlparse(raw_base)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise PermissionError(
                "IRAS_DEVICE_OLLAMA_BASE_URL must be a loopback http:// endpoint."
            )
        root = raw_base[:-3] if raw_base.endswith("/v1") else raw_base
        started = time.perf_counter()
        try:
            with httpx.Client(
                timeout=httpx.Timeout(connect=1.5, read=2.5, write=2.5, pool=1.5),
                follow_redirects=False,
            ) as client:
                response = client.get(root + "/api/tags")
                response.raise_for_status()
                body = response.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(
                "Local Ollama is not reachable at 127.0.0.1:11434."
            ) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError("Local Ollama status probe timed out.") from exc
        models = [
            str(item.get("name") or "")
            for item in (body.get("models") or [])
            if isinstance(item, dict) and item.get("name")
        ]
        preferred = [
            item.strip()
            for item in os.getenv(
                "IRAS_DEVICE_OLLAMA_MODELS",
                "qwen2.5-coder:7b,qwen2.5-coder:1.5b,llama3.1:8b,llama3",
            ).split(",")
            if item.strip()
        ]
        names_fold = {name.casefold(): name for name in models}
        selected = ""
        for candidate in preferred:
            if candidate.casefold() in names_fold:
                selected = names_fold[candidate.casefold()]
                break
        if not selected and models:
            selected = sorted(
                models,
                key=lambda name: (
                    0 if "coder" in name.casefold() else 1,
                    0 if "qwen" in name.casefold() else 1,
                    name.casefold(),
                ),
            )[0]
        return {
            "ready": bool(models),
            "models": models[:32],
            "selected_model": selected,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "endpoint": "loopback",
        }

    def local_llm_complete(
        self,
        messages,
        tools=None,
        model: str = "",
        max_tokens: int = 900,
        temperature: float = 0.15,
        timeout: float = 120.0,
    ):
        """Run a bounded OpenAI-compatible chat completion on local Ollama.

        This action is deliberately loopback-only. It is a reasoning fallback,
        not a network proxy. Returned tool calls are data; execution still goes
        back through IRAS Cloud's ToolRegistry and normal permission gates.
        """
        raw_base = os.getenv(
            "IRAS_DEVICE_OLLAMA_BASE_URL",
            "http://127.0.0.1:11434/v1",
        ).strip().rstrip("/")
        parsed = urlparse(raw_base)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise PermissionError(
                "IRAS_DEVICE_OLLAMA_BASE_URL must be a loopback http:// endpoint."
            )
        if parsed.username or parsed.password:
            raise PermissionError("Credentials are not allowed in the local Ollama URL.")

        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty list.")
        messages = [item for item in messages[-32:] if isinstance(item, dict)]
        if not messages:
            raise ValueError("messages contained no usable entries.")
        serialized_messages = json.dumps(messages, ensure_ascii=False)
        if len(serialized_messages) > 80_000:
            raise ValueError("Local LLM message payload exceeds the 80k character limit.")

        tools = [item for item in (tools or [])[:48] if isinstance(item, dict)]
        if len(json.dumps(tools, ensure_ascii=False)) > 60_000:
            raise ValueError("Local LLM tool schema payload exceeds the 60k character limit.")

        timeout = max(10.0, min(float(timeout), 150.0))
        max_tokens = max(64, min(int(max_tokens), 2048))
        temperature = max(0.0, min(float(temperature), 1.0))

        requested = str(model or "").strip()
        preferred = [
            item.strip()
            for item in os.getenv(
                "IRAS_DEVICE_OLLAMA_MODELS",
                "qwen2.5-coder:7b,qwen2.5-coder:1.5b,llama3.1:8b,llama3",
            ).split(",")
            if item.strip()
        ]

        try:
            root = raw_base[:-3] if raw_base.endswith("/v1") else raw_base
            with httpx.Client(
                timeout=httpx.Timeout(connect=2.5, read=timeout, write=15.0, pool=5.0),
                follow_redirects=False,
            ) as client:
                installed = []
                try:
                    tags = client.get(root + "/api/tags")
                    if tags.status_code < 400:
                        installed = [
                            str(item.get("name") or "")
                            for item in (tags.json().get("models") or [])
                            if isinstance(item, dict) and item.get("name")
                        ]
                except Exception:
                    installed = []

                chosen = requested
                if installed:
                    names_fold = {name.casefold(): name for name in installed}
                    if chosen and chosen.casefold() not in names_fold:
                        chosen = ""
                    elif chosen:
                        chosen = names_fold[chosen.casefold()]
                    if not chosen:
                        for candidate in preferred:
                            if candidate.casefold() in names_fold:
                                chosen = names_fold[candidate.casefold()]
                                break
                    if not chosen:
                        # Prefer coder/qwen models over arbitrary embeddings etc.
                        ranked = sorted(
                            installed,
                            key=lambda name: (
                                0 if "coder" in name.casefold() else 1,
                                0 if "qwen" in name.casefold() else 1,
                                name.casefold(),
                            ),
                        )
                        chosen = ranked[0] if ranked else ""
                if not chosen:
                    chosen = requested or (preferred[0] if preferred else "qwen2.5-coder:7b")

                payload = {
                    "model": chosen,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"
                response = client.post(raw_base + "/chat/completions", json=payload)
                if response.status_code >= 400:
                    detail = response.text[:1000]
                    raise RuntimeError(
                        f"Local Ollama HTTP {response.status_code}: {detail}"
                    )
                body = response.json()
        except httpx.ConnectError as exc:
            raise RuntimeError(
                "Local Ollama is not reachable at 127.0.0.1:11434. Start Ollama on the Windows PC."
            ) from exc
        except httpx.TimeoutException as exc:
            raise RuntimeError("Local Ollama timed out while generating a fallback response.") from exc
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Local Ollama returned an unexpected response format.") from exc

        try:
            msg = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Local Ollama response did not contain an assistant message.") from exc

        normalized_calls = []
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            if not isinstance(fn, dict):
                continue
            normalized_calls.append(
                {
                    "id": str(tc.get("id") or ""),
                    "name": str(fn.get("name") or ""),
                    "arguments": fn.get("arguments") or {},
                }
            )
        return {
            "model": str(body.get("model") or chosen),
            "content": msg.get("content") or "",
            "tool_calls": normalized_calls,
            "local": True,
        }

    def run_tests(
        self,
        project: str,
        target: str = "",
        timeout: float = 180.0,
    ):
        project_path = self._path(
            project
        )

        if not project_path.is_dir():
            raise NotADirectoryError(
                project_path
            )

        command = None
        runner = None

        if (
            (
                project_path
                / "pyproject.toml"
            ).exists()
            or (
                project_path
                / "pytest.ini"
            ).exists()
            or (
                project_path
                / "setup.cfg"
            ).exists()
        ):
            command = [
                sys.executable,
                "-m",
                "pytest",
                "-q",
            ]
            runner = "pytest"
            target = str(target or "").strip()
            if target:
                if target.startswith("-") or "\x00" in target or "\n" in target or "\r" in target:
                    raise ValueError("Invalid pytest target.")
                file_part, sep, node_part = target.partition("::")
                candidate = (project_path / file_part).resolve()
                try:
                    relative = candidate.relative_to(project_path)
                except ValueError as exc:
                    raise PermissionError("Test target must stay inside the project.") from exc
                if not candidate.exists():
                    raise FileNotFoundError(candidate)
                command.append(str(relative) + (("::" + node_part) if sep else ""))

        elif (
            project_path
            / "package.json"
        ).exists():
            if str(target or "").strip():
                raise ValueError("Targeted test selection is currently supported only for pytest projects.")
            package = json.loads(
                (
                    project_path
                    / "package.json"
                ).read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            )

            if not (
                package.get("scripts")
                or {}
            ).get("test"):
                raise RuntimeError(
                    "package.json has no test script."
                )

            if (
                project_path
                / "pnpm-lock.yaml"
            ).exists():
                executable = (
                    shutil.which(
                        "pnpm"
                    )
                    or shutil.which(
                        "pnpm.cmd"
                    )
                )
                if not executable:
                    raise FileNotFoundError(
                        "pnpm is not installed."
                    )
                command = [
                    executable,
                    "test",
                ]
                runner = "pnpm"
            else:
                executable = (
                    shutil.which(
                        "npm"
                    )
                    or shutil.which(
                        "npm.cmd"
                    )
                )
                if not executable:
                    raise FileNotFoundError(
                        "npm is not installed."
                    )
                command = [
                    executable,
                    "test",
                ]
                runner = "npm"

        else:
            raise RuntimeError(
                "IRAS could not detect a supported test runner."
            )

        result = subprocess.run(
            command,
            cwd=project_path,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=max(10.0, min(float(timeout), 180.0)),
            shell=False,
        )

        return {
            "project": str(
                project_path
            ),
            "runner": runner,
            "returncode": (
                result.returncode
            ),
            "stdout": (
                result.stdout[-30000:]
            ),
            "stderr": (
                result.stderr[-12000:]
            ),
        }

    def interact_app(
        self,
        app: str,
        actions,
        ensure_open: bool = True,
    ):
        return self.ui.interact(
            app,
            actions,
            ensure_open=bool(
                ensure_open
            ),
        )

    def observe_ui(
        self,
        app: str,
        ensure_open: bool = True,
        max_elements: int = 180,
        screenshot: bool = True,
    ):
        return self.visual.observe(
            app,
            ensure_open=bool(
                ensure_open
            ),
            max_elements=max_elements,
            screenshot=bool(
                screenshot
            ),
        )

    def semantic_action(
        self,
        app: str,
        action: str,
        target: str,
        text: str = "",
        key: str = "",
        role: str = "",
        occurrence: int = 1,
        replace: bool = False,
        ensure_open: bool = True,
        verify: bool = True,
    ):
        return self.visual.act(
            app,
            action,
            target,
            text=text,
            key=key,
            role=role,
            occurrence=occurrence,
            replace=bool(
                replace
            ),
            ensure_open=bool(
                ensure_open
            ),
            verify=bool(
                verify
            ),
        )

    def computer_status(self):
        return self.computer.status()

    def computer_observe(
        self,
        vision: str = "auto",
        scope: str = "auto",
        max_elements: int = 180,
    ):
        return self.computer.observe(
            vision=vision,
            scope=scope,
            max_elements=max_elements,
        )

    def computer_action(
        self,
        observation_id: str,
        action: str,
        element_id: str = "",
        target_element_id: str = "",
        text: str = "",
        key: str = "",
        keys=None,
        amount: int = 0,
        replace: bool = False,
        seconds: float = 0.5,
        verify: bool = True,
    ):
        return self.computer.action(
            observation_id=observation_id,
            action=action,
            element_id=element_id,
            target_element_id=target_element_id,
            text=text,
            key=key,
            keys=keys,
            amount=amount,
            replace=replace,
            seconds=seconds,
            verify=verify,
        )

    def computer_verify(
        self,
        condition: str,
        target: str = "",
        prior_observation_id: str = "",
        vision: str = "auto",
        scope: str = "auto",
    ):
        return self.computer.verify(
            condition=condition,
            target=target,
            prior_observation_id=prior_observation_id,
            vision=vision,
            scope=scope,
        )

    def whatsapp_open_chat(
        self,
        contact: str,
    ):
        return open_whatsapp_chat_and_verify(
            self.ui,
            self.computer,
            contact=contact,
        )

    def spotify_search(
        self,
        query: str,
    ):
        return self.ui.spotify_search(
            query
        )

    def spotify_play(
        self,
        query: str,
    ):
        return self.ui.spotify_play(
            query
        )

    def media_control(
        self,
        command: str,
        app: str | None = None,
    ):
        return self.ui.media_control(
            command,
            app=app,
        )

    def capture_screen(
        self,
    ):
        from PIL import (
            ImageGrab,
        )

        target = (
            Path.home()
            / ".iras"
            / "screenshots"
            / (
                "screen-"
                + str(
                    int(
                        time.time()
                    )
                )
                + ".jpg"
            )
        )

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        image = ImageGrab.grab(
            all_screens=True
        )

        image.thumbnail(
            (
                1600,
                1000,
            )
        )

        image.convert(
            "RGB"
        ).save(
            target,
            "JPEG",
            quality=78,
            optimize=True,
        )

        return {
            "path": str(
                target
            ),
            "width": image.width,
            "height": image.height,
            "bytes": (
                target.stat().st_size
            ),
        }


    def screen_preview(self, max_width: int = 1100, quality: int = 62):
        """Return a bounded JPEG preview suitable for an authenticated remote UI."""
        from PIL import ImageGrab

        max_width = max(480, min(int(max_width), 1600))
        quality = max(40, min(int(quality), 82))
        image = ImageGrab.grab(all_screens=True).convert("RGB")
        source_size = image.size
        if image.width > max_width:
            ratio = max_width / float(image.width)
            image = image.resize((max_width, max(1, int(image.height * ratio))))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        raw = buffer.getvalue()
        if len(raw) > 2_500_000:
            raise RuntimeError("Remote screen preview exceeded the bounded payload size.")
        return {
            "mime": "image/jpeg",
            "base64": base64.b64encode(raw).decode("ascii"),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "width": image.width,
            "height": image.height,
            "source_width": source_size[0],
            "source_height": source_size[1],
            "bytes": len(raw),
        }

    def list_processes(self, limit: int = 300):
        limit = max(1, min(int(limit), 1000))
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=20,
                shell=False,
            )
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            return {"processes": lines[:limit], "returncode": result.returncode}
        result = subprocess.run(
            ["ps", "-eo", "pid,comm,%cpu,%mem"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=20,
            shell=False,
        )
        return {"processes": result.stdout.splitlines()[:limit], "returncode": result.returncode}

    def kill_process(self, pid: int):
        pid = int(pid)
        if pid <= 0:
            raise ValueError("pid must be positive.")
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=20,
                shell=False,
            )
        else:
            result = subprocess.run(
                ["kill", "-TERM", str(pid)],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=20,
                shell=False,
            )
        return {"pid": pid, "returncode": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}

    @staticmethod
    def _atomic_write_text(target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        old_mode = None
        if target.exists():
            try:
                old_mode = target.stat().st_mode
            except OSError:
                old_mode = None
        fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".iras-tmp", dir=str(target.parent))
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if old_mode is not None:
                try:
                    os.chmod(temp_path, old_mode)
                except OSError:
                    pass
            os.replace(temp_path, target)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def write_text(self, path: str, content: str, append: bool = False):
        target = self._path(path, must_exist=False)
        text = str(content)
        if len(text.encode("utf-8")) > 2_000_000:
            raise ValueError("write_text payload is limited to 2 MB.")
        if append:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
        else:
            self._atomic_write_text(target, text)
        return {"path": str(target), "bytes": target.stat().st_size, "append": bool(append), "atomic": not bool(append)}

    def replace_text(
        self,
        path: str,
        old_text: str,
        new_text: str,
        count: int = 1,
    ):
        """Replace an exact snippet inside an allowed text file.

        This is intentionally narrower than arbitrary shell/editor control: the
        expected old text must be present, replacement count is bounded, and the
        file stays inside IRAS_BRIDGE_ROOTS.
        """
        target = self._path(path)
        if not target.is_file():
            raise FileNotFoundError(target)
        if target.stat().st_size > 2_000_000:
            raise ValueError("replace_text refuses files larger than 2 MB.")
        old_text = str(old_text or "")
        new_text = str(new_text or "")
        if not old_text:
            raise ValueError("old_text must not be empty.")
        if len(old_text) > 50_000 or len(new_text) > 50_000:
            raise ValueError("replace_text snippets are limited to 50,000 characters.")
        count = max(1, min(int(count), 20))
        original = target.read_text(encoding="utf-8", errors="strict")
        available = original.count(old_text)
        if available < count:
            raise ValueError(
                f"Expected snippet occurs {available} time(s); need at least {count}."
            )
        updated = original.replace(old_text, new_text, count)
        if updated == original:
            raise RuntimeError("replace_text made no change.")
        self._atomic_write_text(target, updated)
        return {
            "path": str(target),
            "replacements": count,
            "bytes": target.stat().st_size,
        }

    def make_directory(self, path: str):
        target = self._path(path, must_exist=False)
        target.mkdir(parents=True, exist_ok=True)
        return {"path": str(target), "created": True}

    def copy_path(self, source: str, destination: str):
        src = self._path(source)
        dst = self._path(destination, must_exist=False)
        if src.is_dir():
            for child in src.rglob("*"):
                if child.is_symlink():
                    raise PermissionError("copy_path refuses directory trees containing symlinks.")
            shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=False)
        else:
            if src.is_symlink():
                raise PermissionError("copy_path refuses symbolic links.")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return {"source": str(src), "destination": str(dst)}

    def move_path(self, source: str, destination: str):
        src = self._path(source)
        dst = self._path(destination, must_exist=False)
        dst.parent.mkdir(parents=True, exist_ok=True)
        moved = shutil.move(str(src), str(dst))
        return {"source": str(src), "destination": str(Path(moved))}

    def delete_path(self, path: str):
        target = self._path(path)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"deleted": str(target)}

    @staticmethod
    def _clipboard_root():
        if os.name != "nt":
            raise RuntimeError("Remote clipboard control is currently Windows-only.")
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        return root

    def clipboard_get(self):
        root = self._clipboard_root()
        try:
            try:
                text = root.clipboard_get()
            except Exception:
                text = ""
            return {"text": str(text)[:100000]}
        finally:
            root.destroy()

    def clipboard_set(self, text: str):
        root = self._clipboard_root()
        try:
            root.clipboard_clear()
            root.clipboard_append(str(text))
            root.update()
            return {"set": True, "chars": len(str(text))}
        finally:
            root.destroy()

    def ui_find_text(self, text: str, exact: bool = False, role: str = "", vision: str = "auto"):
        return self.primitives.find_text(text, exact=bool(exact), role=role, vision=vision)

    def ui_click_text(self, text: str, exact: bool = False, role: str = "", vision: str = "auto", verify_text: str = ""):
        return self.primitives.click_text(text, exact=bool(exact), role=role, vision=vision, verify_text=verify_text)

    def ui_type_text(self, target: str, text: str, replace: bool = True, exact: bool = False, role: str = "", vision: str = "auto"):
        return self.primitives.type_into_text(target, text, replace=bool(replace), exact=bool(exact), role=role, vision=vision)

    def ui_wait_text(self, text: str, timeout: float = 8.0, exact: bool = False, role: str = "", vision: str = "auto"):
        return self.primitives.wait_text(text, timeout=timeout, exact=bool(exact), role=role, vision=vision)

    def ui_scroll_until_text(self, text: str, amount: int = -620, max_steps: int = 6, vision: str = "auto"):
        return self.primitives.scroll_until_text(text, amount=amount, max_steps=max_steps, vision=vision)

    def verify_state(self, kind: str, target: str = "", vision: str = "auto", scope: str = "foreground"):
        return self.verifier.verify(kind, target, vision=vision, scope=scope)

    def power_action(self, action: str):
        action = str(action or "").strip().lower()
        if os.name != "nt":
            raise RuntimeError("Remote power actions are Windows-only.")
        if action == "lock":
            import ctypes
            if not ctypes.windll.user32.LockWorkStation():
                raise RuntimeError("Windows refused to lock the workstation.")
            return {"action": action, "requested": True}
        mapping = {
            "restart": ["shutdown.exe", "/r", "/t", "5", "/c", "IRAS remote restart"],
            "shutdown": ["shutdown.exe", "/s", "/t", "5", "/c", "IRAS remote shutdown"],
        }
        command = mapping.get(action)
        if not command:
            raise ValueError("power_action supports lock, restart, or shutdown.")
        process = subprocess.Popen(command, shell=False)
        return {"action": action, "requested": True, "pid": process.pid, "delay_seconds": 5}


    def software_manager_status(self):
        return software_manager_status_impl()

    def software_search(self, query: str, source: str = "winget", count: int = 20):
        return software_search_impl(query, source=source, count=count)

    def software_show(self, package_id: str, source: str = "winget"):
        return software_show_impl(package_id, source=source)

    def software_list(self, query: str = "", package_id: str = ""):
        return software_list_impl(query=query, package_id=package_id)

    def software_upgrades(self, package_id: str = "", source: str = "winget"):
        return software_upgrades_impl(package_id=package_id, source=source)

    def software_install(self, package_id: str, source: str = "winget", version: str = "", scope: str = ""):
        return software_install_impl(package_id, source=source, version=version, scope=scope)

    def software_upgrade(self, package_id: str = "", source: str = "winget", all_packages: bool = False):
        return software_upgrade_impl(package_id, source=source, all_packages=all_packages)

    def software_uninstall(self, package_id: str, source: str = "winget"):
        return software_uninstall_impl(package_id, source=source)

    def software_prepare_url(self, url: str):
        return software_prepare_url_impl(url)

    def software_install_prepared(self, receipt_id: str):
        return software_install_prepared_impl(receipt_id)

    def run_command(
        self,
        executable: str,
        args=None,
        cwd: str = "",
        timeout: float = 60.0,
    ):
        """Run one explicitly named executable with argv and shell=False.

        This is intentionally classified as CRITICAL by remote policy. It becomes
        available only when the laptop is locally armed for full mode with the
        shell/command opt-in and the cloud request carries a full remote session.
        """
        executable = str(executable or "").strip()
        if not executable:
            raise ValueError("executable is required.")
        if any(ch in executable for ch in "\r\n\x00"):
            raise ValueError("Invalid executable name.")
        resolved = shutil.which(executable)
        if not resolved:
            candidate = Path(executable).expanduser()
            if candidate.is_file():
                resolved = str(candidate.resolve())
        if not resolved:
            raise FileNotFoundError(f"Executable {executable!r} was not found.")
        argv = [str(resolved)] + [str(item) for item in (args or [])[:64]]
        workdir = None
        if cwd:
            workdir = self._path(cwd)
            if not workdir.is_dir():
                raise NotADirectoryError(workdir)
        timeout = max(1.0, min(float(timeout), 300.0))
        completed = subprocess.run(
            argv,
            cwd=str(workdir) if workdir else None,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            shell=False,
        )
        return {
            "executable": str(resolved),
            "args": argv[1:],
            "cwd": str(workdir) if workdir else None,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-30000:],
            "stderr": completed.stderr[-12000:],
        }
