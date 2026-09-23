from __future__ import annotations

import json
import os
from pathlib import Path

from iras.security.secret_store import unprotect_secret


def _bridge_config_path() -> Path:
    return Path.home() / ".iras-device-bridge.json"


def paired_api_token() -> str:
    """Return the DPAPI-protected token from the verified device pairing, if available."""
    path = _bridge_config_path()
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        protected = str(data.get("api_token_protected") or "").strip()
        if protected:
            return str(unprotect_secret(protected) or "").strip()
        # Backward compatibility only; new pairing code rewrites plaintext.
        return str(data.get("api_token") or "").strip()
    except Exception:
        return ""


def cloud_token_candidates(settings=None, override: str = "") -> list[tuple[str, str]]:
    """Return unique cloud-auth candidates without ever logging token contents."""
    raw = [
        ("explicit", str(override or "").strip()),
        ("IRAS_CLOUD_TOKEN", os.getenv("IRAS_CLOUD_TOKEN", "").strip()),
        ("paired-device", paired_api_token()),
        ("IRAS_API_TOKEN", str(getattr(settings, "api_token", "") or "").strip()),
    ]
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source, token in raw:
        if not token or token == "change-me-before-remote-use" or token in seen:
            continue
        seen.add(token)
        result.append((source, token))
    return result


def resolve_cloud_token(settings=None, override: str = "") -> tuple[str, str]:
    candidates = cloud_token_candidates(settings, override)
    return candidates[0] if candidates else ("", "")
