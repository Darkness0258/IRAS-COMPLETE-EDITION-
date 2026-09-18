from __future__ import annotations

import platform
import socket
from typing import Any

from iras import __version__
from iras.device_bridge.executor import DEFAULT_CAPABILITIES, DeviceExecutor


class LocalDeviceBridgeStore:
    """Synchronous in-process adapter for controlling the current PC.

    The cloud runtime queues device commands through ``DeviceBridgeStore``.
    The desktop/CLI runtime already runs on the target computer, so routing the
    same bounded device-tool contract through a local ``DeviceExecutor`` avoids
    unnecessary shell fallbacks while preserving the strict non-shell executor.
    """

    DEVICE_ID = "local-windows"

    def __init__(self, executor: DeviceExecutor | None = None):
        self.executor = executor or DeviceExecutor()
        self.display_name = socket.gethostname() or "Local Windows PC"

    def list_devices(self) -> list[dict[str, Any]]:
        return [
            {
                "device_id": self.DEVICE_ID,
                "display_name": self.display_name,
                "platform": platform.platform(),
                "capabilities": list(DEFAULT_CAPABILITIES),
                "app_version": __version__,
                "enabled": True,
                "online": True,
                "local": True,
            }
        ]

    def request_and_wait(
        self,
        *,
        action: str,
        arguments: dict,
        device_id: str | None = None,
        timeout: float = 30.0,
        remote_session_id: str | None = None,
        permission_level: int | None = None,
        requester_device: str = "cloud-agent",
    ):
        # Keep the same keyword contract as DeviceBridgeStore so the shared
        # device-tool layer can route local CLI actions without branching on
        # store type.  The in-process store must never become a shortcut for a
        # remote session, though: remote provenance belongs to the queued cloud
        # store where session authorization is enforced.
        _ = (timeout, requester_device)
        if remote_session_id or permission_level is not None:
            raise PermissionError(
                "Remote-session provenance cannot be executed through the local in-process device store."
            )

        if device_id not in {None, "", self.DEVICE_ID}:
            raise RuntimeError(
                f"Unknown local device_id {device_id!r}; expected {self.DEVICE_ID!r}."
            )

        return self.executor.execute(
            str(action),
            dict(arguments or {}),
        )
