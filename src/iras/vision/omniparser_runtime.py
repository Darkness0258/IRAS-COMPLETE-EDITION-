from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import threading
import time
from urllib.parse import urlparse

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:8010"


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "enabled"}


@dataclass(frozen=True)
class RuntimeProbe:
    ready: bool
    status: str
    reason: str = ""
    pid: int | None = None
    started_by_iras: bool = False
    base_url: str = DEFAULT_BASE_URL

    def as_dict(self) -> dict:
        return {
            "ready": bool(self.ready),
            "status": self.status,
            "reason": self.reason or None,
            "pid": self.pid,
            "started_by_iras": bool(self.started_by_iras),
            "base_url": self.base_url,
        }


class OmniParserRuntimeManager:
    """Own the on-demand local OmniParser lifecycle used by IRAS vision.

    IRAS never downloads weights or installs dependencies. When visual grounding
    is actually needed, the manager first probes the configured endpoint. If the
    endpoint is loopback and unavailable, it may start a *configured/discovered*
    OmniParser process with ``shell=False`` and wait for ``/probe/``.

    This keeps OmniParser lazy (zero idle cost before vision is needed), avoids
    duplicate servers, and removes the need to manually start it before every
    WebView/custom-rendered task.
    """

    _lock = threading.Lock()

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._started_by_iras = False
        self._last_start_error = ""
        self._last_start_attempt = 0.0

    @staticmethod
    def autostart_enabled() -> bool:
        return _truthy("IRAS_OMNIPARSER_AUTOSTART", default=True)

    @classmethod
    def base_url(cls) -> str:
        raw = os.getenv("IRAS_OMNIPARSER_URL", "").strip()
        if not raw and cls.autostart_enabled():
            raw = DEFAULT_BASE_URL
        return raw.rstrip("/")

    @classmethod
    def parse_url(cls) -> str:
        raw = cls.base_url()
        if not raw:
            return ""
        if raw.endswith("/parse"):
            return raw + "/"
        return raw + "/parse/"

    @classmethod
    def probe_url(cls) -> str:
        raw = cls.base_url()
        if not raw:
            return ""
        if raw.endswith("/parse"):
            raw = raw[:-6].rstrip("/")
        return raw + "/probe/"

    @staticmethod
    def headers() -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = os.getenv("IRAS_OMNIPARSER_API_KEY", "").strip()
        if key:
            headers["Authorization"] = "Bearer " + key
        return headers

    @classmethod
    def _is_local_endpoint(cls) -> bool:
        raw = cls.base_url()
        if not raw:
            return False
        try:
            parsed = urlparse(raw)
        except Exception:
            return False
        host = (parsed.hostname or "").strip().lower()
        return host in {"127.0.0.1", "localhost", "::1"}

    @staticmethod
    def _port() -> int:
        raw = OmniParserRuntimeManager.base_url()
        try:
            parsed = urlparse(raw)
            return int(parsed.port or (443 if parsed.scheme == "https" else 80))
        except Exception:
            return 8010

    @staticmethod
    def _host() -> str:
        raw = OmniParserRuntimeManager.base_url()
        try:
            parsed = urlparse(raw)
            host = parsed.hostname or "127.0.0.1"
            return "127.0.0.1" if host == "localhost" else host
        except Exception:
            return "127.0.0.1"

    @staticmethod
    def _runtime_state_path() -> Path:
        root = Path.home() / ".iras" / "omniparser"
        root.mkdir(parents=True, exist_ok=True)
        return root / "runtime.json"

    @classmethod
    def _read_runtime_state(cls) -> dict:
        path = cls._runtime_state_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @classmethod
    def _write_runtime_state(cls, pid: int) -> None:
        path = cls._runtime_state_path()
        payload = {
            "pid": int(pid),
            "base_url": cls.base_url(),
            "started_by_iras": True,
            "started_at": time.time(),
        }
        temp = path.with_suffix(".tmp")
        try:
            temp.write_text(
                json.dumps(payload, ensure_ascii=True, sort_keys=True),
                encoding="utf-8",
            )
            temp.replace(path)
        except Exception:
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass

    @classmethod
    def _clear_runtime_state(cls, *, pid: int | None = None) -> None:
        path = cls._runtime_state_path()
        if pid is not None:
            state = cls._read_runtime_state()
            try:
                recorded = int(state.get("pid") or 0)
            except (TypeError, ValueError):
                recorded = 0
            if recorded and recorded != int(pid):
                return
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return False
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except PermissionError:
            # Windows can deny PROCESS_QUERY access for a live process. Treat
            # access denied as live rather than discarding IRAS ownership.
            return os.name == "nt"
        except OSError:
            return False
        except Exception:
            return False
        return True

    @classmethod
    def _owned_runtime_pid(cls) -> int | None:
        state = cls._read_runtime_state()
        if not state or state.get("started_by_iras") is not True:
            return None
        if str(state.get("base_url") or "").rstrip("/") != cls.base_url():
            return None
        try:
            pid = int(state.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        if not cls._pid_alive(pid):
            cls._clear_runtime_state(pid=pid or None)
            return None
        return pid

    def probe(self, *, timeout: float | None = None) -> RuntimeProbe:
        base = self.base_url()
        if not base:
            return RuntimeProbe(
                ready=False,
                status="disabled",
                reason="IRAS_OMNIPARSER_URL is not configured and autostart is disabled.",
                started_by_iras=bool(self._started_by_iras or self._owned_runtime_pid()),
                pid=(
                    self._process.pid
                    if self._process is not None and self._process.poll() is None
                    else self._owned_runtime_pid()
                ),
                base_url="",
            )

        probe = self.probe_url()
        process_pid = (
            self._process.pid
            if self._process is not None and self._process.poll() is None
            else None
        )
        owned_pid = process_pid or self._owned_runtime_pid()
        started_by_iras = bool(self._started_by_iras or owned_pid)
        timeout_value = timeout
        if timeout_value is None:
            timeout_value = max(
                0.5,
                min(float(os.getenv("IRAS_OMNIPARSER_PROBE_TIMEOUT", "4")), 15.0),
            )
        try:
            with httpx.Client(timeout=float(timeout_value)) as client:
                response = client.get(probe, headers=self.headers())
                response.raise_for_status()
            return RuntimeProbe(
                ready=True,
                status="ready",
                pid=owned_pid,
                started_by_iras=started_by_iras,
                base_url=base,
            )
        except Exception as exc:
            return RuntimeProbe(
                ready=False,
                status="unreachable",
                reason=f"{type(exc).__name__}: {exc}",
                pid=owned_pid,
                started_by_iras=started_by_iras,
                base_url=base,
            )

    @staticmethod
    def _candidate_roots() -> list[Path]:
        values: list[Path] = []
        explicit = os.getenv("IRAS_OMNIPARSER_ROOT", "").strip()
        if explicit:
            values.append(Path(explicit).expanduser())

        home = Path.home()
        for candidate in (
            Path("D:/Projects/OmniParser"),
            Path("D:/Projects/OmniParser-v2"),
            Path("C:/workstation/Projects/OmniParser"),
            home / "Projects" / "OmniParser",
            home / "OmniParser",
            home / ".iras" / "OmniParser",
        ):
            values.append(candidate)

        output: list[Path] = []
        seen = set()
        for value in values:
            try:
                resolved = value.resolve()
            except Exception:
                continue
            key = str(resolved).casefold()
            if key in seen:
                continue
            seen.add(key)
            if resolved.exists() and resolved.is_dir():
                output.append(resolved)
        return output

    @staticmethod
    def _python_for_root(root: Path) -> str | None:
        candidates = []
        if os.name == "nt":
            candidates.extend(
                [
                    root / ".venv" / "Scripts" / "python.exe",
                    root / "venv" / "Scripts" / "python.exe",
                    root / "env" / "Scripts" / "python.exe",
                    root / "omnitool" / ".venv" / "Scripts" / "python.exe",
                ]
            )
        else:
            candidates.extend(
                [
                    root / ".venv" / "bin" / "python",
                    root / "venv" / "bin" / "python",
                    root / "env" / "bin" / "python",
                ]
            )
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return shutil.which("python") or shutil.which("python3")

    @staticmethod
    def _server_workdir(root: Path) -> Path:
        explicit = os.getenv("IRAS_OMNIPARSER_SERVER_CWD", "").strip()
        if explicit:
            path = Path(explicit).expanduser()
            if path.exists() and path.is_dir():
                return path

        for candidate in (
            root / "omnitool" / "omniparserserver",
            root / "omnitool",
            root,
        ):
            if candidate.exists() and candidate.is_dir():
                return candidate
        return root

    @staticmethod
    def _custom_command() -> list[str] | None:
        raw_json = os.getenv("IRAS_OMNIPARSER_START_JSON", "").strip()
        if raw_json:
            try:
                value = json.loads(raw_json)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "IRAS_OMNIPARSER_START_JSON must be a JSON array of argv strings."
                ) from exc
            if not isinstance(value, list) or not value or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise RuntimeError(
                    "IRAS_OMNIPARSER_START_JSON must be a non-empty JSON array of argv strings."
                )
            return [str(item) for item in value]

        raw = os.getenv("IRAS_OMNIPARSER_START_COMMAND", "").strip()
        if raw:
            # This is argv parsing only; subprocess still runs with shell=False.
            return shlex.split(raw, posix=os.name != "nt")
        return None

    def _build_command(self) -> tuple[list[str], Path | None]:
        custom = self._custom_command()
        roots = self._candidate_roots()
        if custom:
            cwd = roots[0] if roots else None
            return custom, cwd

        if not roots:
            raise RuntimeError(
                "OmniParser is not running and IRAS could not discover its local folder. "
                "Set IRAS_OMNIPARSER_ROOT or IRAS_OMNIPARSER_START_JSON once; IRAS will "
                "then start it automatically whenever visual grounding is needed."
            )

        root = roots[0]
        python = self._python_for_root(root)
        if not python:
            raise RuntimeError(
                f"No Python executable was found for OmniParser at {root}."
            )

        workdir = self._server_workdir(root)
        device = os.getenv("IRAS_OMNIPARSER_DEVICE", "cpu").strip() or "cpu"
        caption_model = (
            os.getenv("IRAS_OMNIPARSER_CAPTION_MODEL", "florence2").strip()
            or "florence2"
        )
        caption_path = os.getenv(
            "IRAS_OMNIPARSER_CAPTION_MODEL_PATH",
            "../../weights/icon_caption_florence",
        ).strip()
        box_threshold = os.getenv("IRAS_OMNIPARSER_BOX_THRESHOLD", "0.05").strip() or "0.05"

        # PaddleOCR 2.x and PyTorch can conflict on Windows if Paddle loads
        # its DLLs before torch. OmniParser requires torch anyway, so preload it
        # explicitly before importing/running the server module. This preserves
        # the normal argv contract while avoiding the WinError 127/shm.dll
        # loader failure seen when PaddleOCR imports albumentations -> torch.
        # Import the OmniParser server module without executing its ``__main__``
        # block, then run uvicorn ourselves with reload disabled. The upstream
        # module enables ``reload=True`` when run as a script, which creates a
        # watcher/child-process pair and makes ownership/PID reporting brittle.
        # A single production server process is faster, easier to supervise, and
        # lets IRAS preserve the exact PID across CLI/runtime-manager instances.
        bootstrap = (
            "import runpy, torch, uvicorn; "
            "ns=runpy.run_module('omniparserserver', "
            "run_name='iras_omniparser_runtime', alter_sys=False); "
            "a=ns['args']; "
            "uvicorn.run(ns['app'], host=a.host, port=a.port, reload=False)"
        )
        command = [
            python,
            "-c",
            bootstrap,
            "--caption_model_name",
            caption_model,
            "--caption_model_path",
            caption_path,
            "--device",
            device,
            "--BOX_TRESHOLD",
            box_threshold,
            "--host",
            self._host(),
            "--port",
            str(self._port()),
        ]
        return command, workdir

    @staticmethod
    def _log_path() -> Path:
        root = Path.home() / ".iras" / "omniparser"
        root.mkdir(parents=True, exist_ok=True)
        return root / "omniparser.log"

    @staticmethod
    def _tail(path: Path, max_chars: int = 2500) -> str:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""
        return text[-max_chars:].strip()

    def _spawn(self) -> subprocess.Popen:
        command, cwd = self._build_command()
        log_path = self._log_path()
        log_handle = open(log_path, "a", encoding="utf-8", errors="replace")
        log_handle.write(
            f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] IRAS autostart: "
            + " ".join(command)
            + "\n"
        )
        log_handle.flush()

        kwargs: dict = {
            "cwd": str(cwd) if cwd else None,
            "stdin": subprocess.DEVNULL,
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
            "shell": False,
        }
        if os.name == "nt":
            kwargs["creationflags"] = int(
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        else:
            kwargs["start_new_session"] = True

        try:
            process = subprocess.Popen(command, **kwargs)
        finally:
            # Popen duplicates the OS handle; parent does not need to keep it.
            log_handle.close()
        return process

    def ensure_ready(self, *, start: bool = True) -> RuntimeProbe:
        first = self.probe()
        if first.ready:
            return first
        if not start:
            return first
        if not self.autostart_enabled():
            return RuntimeProbe(
                ready=False,
                status="autostart_disabled",
                reason=first.reason or "OmniParser autostart is disabled.",
                base_url=self.base_url(),
                pid=first.pid,
                started_by_iras=self._started_by_iras,
            )
        if not self._is_local_endpoint():
            return RuntimeProbe(
                ready=False,
                status="remote_unreachable",
                reason=(
                    "The configured OmniParser endpoint is remote/unreachable. IRAS will not "
                    "start processes for remote endpoints. " + (first.reason or "")
                ).strip(),
                base_url=self.base_url(),
            )

        with self._lock:
            # Another controller/thread may have started it while we waited.
            probe = self.probe(timeout=1.0)
            if probe.ready:
                return probe

            now = time.monotonic()
            if (
                self._last_start_attempt
                and now - self._last_start_attempt < 5.0
                and self._process is not None
                and self._process.poll() is None
            ):
                process = self._process
            else:
                self._last_start_attempt = now
                try:
                    process = self._spawn()
                    self._process = process
                    self._started_by_iras = True
                    self._write_runtime_state(process.pid)
                    self._last_start_error = ""
                except Exception as exc:
                    self._last_start_error = f"{type(exc).__name__}: {exc}"
                    return RuntimeProbe(
                        ready=False,
                        status="autostart_failed",
                        reason=self._last_start_error,
                        base_url=self.base_url(),
                    )

            timeout = max(
                3.0,
                min(float(os.getenv("IRAS_OMNIPARSER_START_TIMEOUT", "45")), 180.0),
            )
            deadline = time.monotonic() + timeout
            last_reason = probe.reason
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    tail = self._tail(self._log_path())
                    reason = f"OmniParser exited during startup with code {process.returncode}."
                    if tail:
                        reason += " Log tail: " + tail
                    self._last_start_error = reason
                    self._clear_runtime_state(pid=process.pid)
                    return RuntimeProbe(
                        ready=False,
                        status="autostart_exited",
                        reason=reason,
                        pid=process.pid,
                        started_by_iras=True,
                        base_url=self.base_url(),
                    )
                probe = self.probe(timeout=1.0)
                if probe.ready:
                    return RuntimeProbe(
                        ready=True,
                        status="ready_autostarted",
                        pid=process.pid,
                        started_by_iras=True,
                        base_url=self.base_url(),
                    )
                last_reason = probe.reason
                time.sleep(0.5)

            reason = "OmniParser did not become ready before the bounded startup timeout."
            if last_reason:
                reason += " Last probe: " + last_reason
            self._last_start_error = reason
            return RuntimeProbe(
                ready=False,
                status="autostart_timeout",
                reason=reason,
                pid=process.pid,
                started_by_iras=True,
                base_url=self.base_url(),
            )

    def status(self) -> dict:
        probe = self.probe(timeout=1.0)
        data = probe.as_dict()
        data.update(
            {
                "autostart_enabled": self.autostart_enabled(),
                "local_endpoint": self._is_local_endpoint(),
                "last_start_error": self._last_start_error or None,
                "log_path": str(self._log_path()),
                "runtime_state_path": str(self._runtime_state_path()),
            }
        )
        return data
