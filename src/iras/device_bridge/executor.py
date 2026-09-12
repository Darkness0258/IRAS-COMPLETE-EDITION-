from __future__ import annotations

import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse
import webbrowser

from iras.tools.system import (
    launch_app,
    system_info,
)
from iras.device_bridge.ui_control import (
    WindowsUIController,
)


DEFAULT_CAPABILITIES = [
    "system_info",
    "open_app",
    "open_url",
    "open_project",
    "list_directory",
    "read_text",
    "git_status",
    "run_tests",
    "capture_screen",
    "interact_app",
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

        self.ui = WindowsUIController()

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

        handlers = {
            "system_info": self.system_info,
            "open_app": self.open_app,
            "open_url": self.open_url,
            "open_project": self.open_project,
            "list_directory": self.list_directory,
            "read_text": self.read_text,
            "git_status": self.git_status,
            "run_tests": self.run_tests,
            "capture_screen": self.capture_screen,
            "interact_app": self.interact_app,
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

    def open_app(
        self,
        app: str,
    ):
        normalized = " ".join(
            str(app)
            .lower()
            .split()
        )

        if normalized not in self.APP_ALIASES:
            raise PermissionError(
                "Remote app launch is limited to approved application aliases."
            )

        return launch_app(
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

            output.append(
                {
                    "name": item.name,
                    "type": (
                        "dir"
                        if item.is_dir()
                        else "file"
                    ),
                    "size": (
                        item.stat().st_size
                        if item.is_file()
                        else None
                    ),
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

    def run_tests(
        self,
        project: str,
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

        elif (
            project_path
            / "package.json"
        ).exists():
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
            timeout=180,
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
