from __future__ import annotations

import re
from typing import Any

IRAS_CLOUD_SERVICE_ID = "iras-cloud"
REMOTE_PROTOCOL_VERSION = 1
MINIMUM_REMOTE_MAJOR = 4


class RemoteCompatibilityError(RuntimeError):
    """Raised when a configured server is not a compatible IRAS remote cloud."""


def _major(version: object) -> int | None:
    text = str(version or "").strip()
    match = re.match(r"^(\d+)(?:\.|$)", text)
    return int(match.group(1)) if match else None


def validate_cloud_health(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise RemoteCompatibilityError(
            "IRAS Cloud /health returned an invalid response. Redeploy the v4 cloud backend."
        )

    service_id = str(payload.get("service_id") or "").strip().lower()
    version = str(payload.get("version") or "").strip()
    protocol = payload.get("remote_protocol")

    if service_id != IRAS_CLOUD_SERVICE_ID:
        raise RemoteCompatibilityError(
            "The configured URL is not an IRAS v4 Cloud endpoint "
            f"(service_id={service_id or 'missing'})."
        )

    try:
        protocol_value = int(protocol)
    except (TypeError, ValueError):
        protocol_value = -1

    if protocol_value != REMOTE_PROTOCOL_VERSION:
        raise RemoteCompatibilityError(
            "IRAS Cloud remote protocol is incompatible "
            f"(server={protocol!r}, required={REMOTE_PROTOCOL_VERSION}). "
            "Redeploy this v4 project to Render before pairing Windows."
        )

    major = _major(version)
    if major is None or major < MINIMUM_REMOTE_MAJOR:
        raise RemoteCompatibilityError(
            "IRAS Cloud is too old for the v4 Windows bridge "
            f"(server version={version or 'missing'}, required major>={MINIMUM_REMOTE_MAJOR}). "
            "Redeploy this v4 project to Render before pairing Windows."
        )

    return {
        "service_id": service_id,
        "version": version,
        "remote_protocol": protocol_value,
        "compatible": True,
    }
