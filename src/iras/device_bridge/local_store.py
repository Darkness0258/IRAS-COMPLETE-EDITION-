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
    ):
        # ``timeout`` is part of the shared cloud/local store contract. Local
        # execution is synchronous, so the bounded executor itself owns any
        # operation-specific timeout behavior.
        _ = timeout

        if device_id not in {None, "", self.DEVICE_ID}:
            raise RuntimeError(
                f"Unknown local device_id {device_id!r}; expected {self.DEVICE_ID!r}."
            )

        return self.executor.execute(
            str(action),
            dict(arguments or {}),
        )
