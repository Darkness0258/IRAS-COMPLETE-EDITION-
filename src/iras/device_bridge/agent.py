from __future__ import annotations

import json
import os
import platform
from pathlib import Path
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
from iras.observability import TraceLogger
from iras.remote_access import RemoteAccessPolicy, action_permission
from iras.security.secret_store import protect_secret, unprotect_secret, protection_backend
from iras.safety_runtime import EmergencyStop


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
        server_url: str = "",
        api_token: str = "",
        *,
        status_callback=None,
    ):
        config = _load_config()
        self.server_url = (
            str(server_url or config.get("server_url") or os.getenv("IRAS_SERVER_URL", ""))
            .strip()
            .rstrip("/")
        )
        raw_api_token = str(api_token or os.getenv("IRAS_API_TOKEN", "")).strip()
        if not raw_api_token:
            try:
                raw_api_token = unprotect_secret(str(config.get("api_token_protected") or ""))
            except Exception:
                raw_api_token = ""
        self.api_token = raw_api_token
        self.status_callback = status_callback
        self.policy = RemoteAccessPolicy()
        self.emergency_stop = EmergencyStop()
        self.trace = TraceLogger()

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

        self.device_id = (
            config.get(
                "device_id"
            )
            or uuid.uuid4().hex
        )
        protected_device_token = str(config.get("device_token_protected") or "")
        legacy_device_token = str(config.get("device_token") or "")
        try:
            self.device_token = unprotect_secret(protected_device_token or legacy_device_token)
        except Exception:
            self.device_token = legacy_device_token

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
                "device_token_protected": protect_secret(self.device_token),
                "api_token_protected": protect_secret(self.api_token),
                "secret_backend": protection_backend(),
                "server_url": self.server_url,
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
        if not self.server_url:
            raise RuntimeError("IRAS_SERVER_URL is not configured for remote access.")
        if not self.api_token:
            raise RuntimeError("IRAS_API_TOKEN is required once to pair this laptop with IRAS Cloud.")
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
                    list(DEFAULT_CAPABILITIES) + [
                        "remote_policy:" + str(self.policy.status().get("mode") or "off"),
                        "outbound_only_bridge",
                    ]
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

        permission_level = command.get("permission_level")
        session_id = str(command.get("remote_session_id") or "")
        try:
            self.emergency_stop.assert_clear()
            required = self.policy.authorize(
                action,
                arguments,
                declared_permission=permission_level,
            )
            with self.trace.operation(
                "remote_device_command",
                command_id=command_id,
                action=action,
                permission=required.name,
                remote_session_id=session_id or None,
            ) as trace:
                trace.stage("authorized", mode=self.policy.status().get("mode"))
                result = self.executor.execute(action, arguments)
                trace.stage("executed")

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

        last_disarmed_notice = 0.0
        while not self.stop_event.is_set():
            try:
                if self.emergency_stop.tripped():
                    if time.monotonic() - last_disarmed_notice > 30:
                        self._status("emergency stop is active; no remote commands will run")
                        last_disarmed_notice = time.monotonic()
                    self.stop_event.wait(2.0)
                    continue
                policy_status = self.policy.status()
                if not policy_status.get("enabled"):
                    if time.monotonic() - last_disarmed_notice > 30:
                        self._status("remote access is locally disarmed")
                        last_disarmed_notice = time.monotonic()
                    self.stop_event.wait(2.0)
                    continue
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



def _migrate_legacy_bridge_secrets(config: dict) -> dict:
    """Rewrite legacy plaintext bridge secrets through the active OS backend."""
    config = dict(config or {})

    legacy_device_token = str(config.get("device_token") or "").strip()
    if legacy_device_token and not str(config.get("device_token_protected") or "").strip():
        config["device_token_protected"] = protect_secret(legacy_device_token)
    config.pop("device_token", None)

    legacy_api_token = str(config.get("api_token") or "").strip()
    if legacy_api_token and not str(config.get("api_token_protected") or "").strip():
        config["api_token_protected"] = protect_secret(legacy_api_token)
    config.pop("api_token", None)

    config["secret_backend"] = protection_backend()
    return config


def configure_remote_bridge(
    *,
    server_url: str,
    api_token: str,
    display_name: str = "",
    allowed_roots: list[str] | None = None,
) -> dict:
    config = _migrate_legacy_bridge_secrets(_load_config())
    server_url = str(server_url or "").strip().rstrip("/")
    api_token = str(api_token or "").strip()
    if not server_url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise ValueError("Remote IRAS server must use HTTPS (localhost is allowed for testing).")
    if len(api_token) < 24:
        raise ValueError("IRAS_API_TOKEN is too short for remote use; use a strong random token.")
    config["server_url"] = server_url
    config["api_token_protected"] = protect_secret(api_token)
    config.pop("api_token", None)
    config.pop("device_token", None)
    config["secret_backend"] = protection_backend()
    if display_name:
        config["display_name"] = str(display_name)[:128]
    if allowed_roots is not None:
        roots = []
        for raw in allowed_roots:
            try:
                path = Path(raw).expanduser().resolve()
            except Exception:
                continue
            if path.exists() and str(path) not in roots:
                roots.append(str(path))
        if not roots:
            raise ValueError("At least one valid allowed root is required.")
        config["allowed_roots"] = roots
    _save_config(config)
    return {
        "configured": True,
        "server_url": server_url,
        "display_name": config.get("display_name") or socket.gethostname(),
        "secret_backend": config["secret_backend"],
        "allowed_roots": config.get("allowed_roots") or DeviceExecutor.default_roots(),
        "config_path": str(CONFIG_PATH),
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(prog="iras-device", description="IRAS outbound-only remote Windows bridge")
    parser.add_argument("--server-url", default="")
    parser.add_argument("--api-token", default="")
    parser.add_argument("--display-name", default="")
    parser.add_argument("--allowed-root", action="append", default=[], help="filesystem root that remote file tools may access; repeatable")
    parser.add_argument("--configure", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    policy = RemoteAccessPolicy()
    if args.status:
        cfg = _load_config()
        safe_cfg = {
            "configured": bool(cfg.get("server_url") and cfg.get("device_id")),
            "server_url": cfg.get("server_url"),
            "device_id": cfg.get("device_id"),
            "display_name": cfg.get("display_name"),
            "allowed_roots": cfg.get("allowed_roots") or [],
            "secret_backend": cfg.get("secret_backend"),
            "device_token_protected": bool(cfg.get("device_token_protected")),
            "api_token_protected": bool(cfg.get("api_token_protected")),
        }
        print(json.dumps({"remote_policy": policy.status(), "bridge_config": safe_cfg}, indent=2, default=str))
        return
    if args.configure:
        print(json.dumps(configure_remote_bridge(
            server_url=args.server_url or os.getenv("IRAS_SERVER_URL", ""),
            api_token=args.api_token or os.getenv("IRAS_API_TOKEN", ""),
            display_name=args.display_name,
            allowed_roots=args.allowed_root or None,
        ), indent=2))
        return

    agent = DeviceBridgeAgent(args.server_url, args.api_token)
    if not agent.server_url:
        raise SystemExit("IRAS remote bridge is not configured. Run iras-device --configure first.")
    agent._status("outbound-only bridge starting; " + json.dumps(agent.policy.status(), separators=(",", ":")))
    agent.start()
    try:
        while agent.thread is not None and agent.thread.is_alive():
            agent.thread.join(timeout=1.0)
    except KeyboardInterrupt:
        pass
    finally:
        agent.stop()


if __name__ == "__main__":
    main()
