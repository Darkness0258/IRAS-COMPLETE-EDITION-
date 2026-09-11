from __future__ import annotations

import json
import os
import platform
from pathlib import Path
import secrets
import socket
import threading
import time
import uuid

import httpx

from iras import __version__
from iras.device_bridge.executor import (
    DEFAULT_CAPABILITIES,
    DeviceExecutor,
)


CONFIG_PATH = (
    Path.home()
    / ".iras-device-bridge.json"
)


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}

    try:
        return json.loads(
            CONFIG_PATH.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def _save_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    CONFIG_PATH.write_text(
        json.dumps(
            data,
            indent=2,
        ),
        encoding="utf-8",
    )

    try:
        os.chmod(
            CONFIG_PATH,
            0o600,
        )
    except OSError:
        pass


class DeviceBridgeAgent:
    """Outbound-only secure bridge from this PC to IRAS Cloud."""

    def __init__(
        self,
        server_url: str,
        api_token: str,
        *,
        status_callback=None,
    ):
        self.server_url = (
            str(server_url)
            .strip()
            .rstrip("/")
        )
        self.api_token = (
            str(api_token)
            .strip()
        )
        self.status_callback = (
            status_callback
        )

        self.stop_event = (
            threading.Event()
        )
        self.thread = None
        self.client = httpx.Client(
            timeout=httpx.Timeout(
                connect=15,
                read=35,
                write=15,
                pool=15,
            ),
            follow_redirects=True,
        )

        config = _load_config()

        self.device_id = (
            config.get(
                "device_id"
            )
            or uuid.uuid4().hex
        )
        self.device_token = (
            config.get(
                "device_token"
            )
            or ""
        )

        self.display_name = (
            config.get(
                "display_name"
            )
            or socket.gethostname()
            or "Windows PC"
        )

        roots = config.get(
            "allowed_roots"
        )

        self.executor = (
            DeviceExecutor(
                roots
                if isinstance(
                    roots,
                    list,
                )
                else None
            )
        )

        self._persist()

    def _persist(self):
        _save_config(
            {
                "device_id": (
                    self.device_id
                ),
                "device_token": (
                    self.device_token
                ),
                "display_name": (
                    self.display_name
                ),
                "allowed_roots": [
                    str(path)
                    for path in (
                        self.executor
                        .allowed_roots
                    )
                ],
            }
        )

    def _status(
        self,
        text: str,
    ):
        print(
            f"[IRAS DEVICE] {text}",
            flush=True,
        )

        if self.status_callback:
            try:
                self.status_callback(
                    text
                )
            except Exception:
                pass

    def start(self):
        if (
            self.thread is not None
            and self.thread.is_alive()
        ):
            return

        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            name="iras-device-bridge",
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        self.stop_event.set()

        try:
            self.client.close()
        except Exception:
            pass

    def _pair(self):
        response = self.client.post(
            (
                self.server_url
                + "/v1/devices/pair"
            ),
            headers={
                "Authorization": (
                    "Bearer "
                    + self.api_token
                ),
                "X-Device-ID": (
                    self.device_id
                ),
            },
            json={
                "device_id": (
                    self.device_id
                ),
                "display_name": (
                    self.display_name
                ),
                "platform": (
                    platform.platform()
                ),
                "capabilities": (
                    DEFAULT_CAPABILITIES
                ),
                "app_version": (
                    __version__
                ),
            },
        )

        response.raise_for_status()
        payload = response.json()

        token = str(
            payload.get(
                "device_token"
            )
            or ""
        )

        if not token:
            raise RuntimeError(
                "IRAS Cloud did not return a device token."
            )

        self.device_token = token
        self._persist()

        self._status(
            "paired securely with IRAS Cloud"
        )

    def _device_headers(self):
        return {
            "X-IRAS-Device-ID": (
                self.device_id
            ),
            "X-IRAS-Device-Token": (
                self.device_token
            ),
        }

    def _poll(self):
        response = self.client.get(
            (
                self.server_url
                + "/v1/device/commands/next"
            ),
            params={
                "timeout": 25,
            },
            headers=(
                self._device_headers()
            ),
        )

        if response.status_code == 401:
            self.device_token = ""
            self._persist()
            raise RuntimeError(
                "DEVICE_REPAIR_REQUIRED"
            )

        response.raise_for_status()

        payload = response.json()

        return payload.get(
            "command"
        )

    def _complete(
        self,
        command_id: str,
        *,
        ok: bool,
        result=None,
        error: str = "",
    ):
        response = self.client.post(
            (
                self.server_url
                + "/v1/device/commands/"
                + command_id
                + "/complete"
            ),
            headers=(
                self._device_headers()
            ),
            json={
                "ok": bool(ok),
                "result": result,
                "error": (
                    str(error)
                    [:8000]
                ),
            },
        )

        response.raise_for_status()

    def _execute(
        self,
        command: dict,
    ):
        command_id = str(
            command["command_id"]
        )
        action = str(
            command["action"]
        )
        arguments = (
            command.get(
                "arguments"
            )
            or {}
        )

        self._status(
            f"executing {action}"
        )

        try:
            result = (
                self.executor.execute(
                    action,
                    arguments,
                )
            )

            self._complete(
                command_id,
                ok=True,
                result=result,
            )

            self._status(
                f"{action} completed"
            )

        except Exception as exc:
            self._complete(
                command_id,
                ok=False,
                error=(
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            )

            self._status(
                f"{action} failed: {exc}"
            )

    def _run(self):
        retry_seconds = 2.0

        while not self.stop_event.is_set():
            try:
                if not self.device_token:
                    self._pair()

                command = self._poll()

                retry_seconds = 2.0

                if command:
                    self._execute(
                        command
                    )

            except Exception as exc:
                if (
                    "DEVICE_REPAIR_REQUIRED"
                    in str(exc)
                ):
                    self.device_token = ""
                    self._persist()

                self._status(
                    "bridge reconnecting: "
                    + str(exc)[:180]
                )

                self.stop_event.wait(
                    retry_seconds
                )

                retry_seconds = min(
                    retry_seconds * 1.6,
                    20.0,
                )
