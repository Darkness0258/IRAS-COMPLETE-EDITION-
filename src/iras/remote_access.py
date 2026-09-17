from __future__ import annotations

"""Local safety policy for IRAS remote Windows administration.

The remote bridge is outbound-only. Even a fully trusted cloud server cannot make
this PC perform an action that exceeds the locally armed mode. This is deliberately
separate from cloud/API authentication: possession of a remote token is not itself
permission to exceed the laptop owner's local policy.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Any

from iras.models import PermissionLevel


POLICY_PATH = Path.home() / ".iras" / "remote_access.json"
KILL_SWITCH_PATH = Path.home() / ".iras" / "REMOTE_DISABLED"

MODE_LEVELS = {
    "off": PermissionLevel.READ - 1,
    "read_only": PermissionLevel.READ,
    "control": PermissionLevel.SYSTEM_ACTION,
    "full": PermissionLevel.CRITICAL,
}

READ_ACTIONS = {
    "system_info",
    "detect_apps",
    "list_directory",
    "read_text",
    "read_text_range",
    "search_text",
    "file_info",
    "find_projects",
    "git_status",
    "git_diff",
    "git_log",
    "capture_screen",
    "screen_preview",
    "observe_ui",
    "computer_status",
    "computer_observe",
    "computer_verify",
    "ui_find_text",
    "ui_wait_text",
    "verify_state",
    "list_processes",
    "clipboard_get",
    "local_llm_complete",
    "local_llm_status",
}

SAFE_ACTIONS = {
    "open_app",
    "open_url",
    "open_project",
}

SYSTEM_ACTIONS = {
    "app_control",
    "interact_app",
    "semantic_action",
    "whatsapp_open_chat",
    "spotify_search",
    "spotify_play",
    "media_control",
    "run_tests",
    "write_text",
    "replace_text",
    "make_directory",
    "copy_path",
    "move_path",
    "clipboard_set",
    "ui_click_text",
    "ui_type_text",
    "ui_scroll_until_text",
}

CRITICAL_ACTIONS = {
    "kill_process",
    "delete_path",
    "power_action",
    "run_command",
}


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


SENSITIVE_PATH_PARTS = {
    ".ssh", ".aws", ".azure", ".gnupg", ".kube", ".docker",
}
SENSITIVE_FILENAMES = {
    ".env", ".env.local", ".npmrc", ".pypirc", "credentials", "credentials.json",
    "id_rsa", "id_ed25519", "known_hosts", "login data", "cookies",
}


def is_sensitive_path(value: Any) -> bool:
    raw = str(value or "").strip().replace("/", "\\").lower()
    if not raw:
        return False
    parts = [part for part in raw.split("\\") if part]
    if any(part in SENSITIVE_PATH_PARTS for part in parts):
        return True
    name = parts[-1] if parts else raw
    if name in SENSITIVE_FILENAMES or name.startswith(".env."):
        return True
    if name.endswith((".pem", ".key", ".p12", ".pfx")):
        return True
    return False


def _file_action_sensitive(action: str, arguments: dict) -> bool:
    if action in {"read_text", "read_text_range", "file_info", "write_text", "replace_text", "delete_path"}:
        return is_sensitive_path(arguments.get("path"))
    if action in {"copy_path", "move_path"}:
        return is_sensitive_path(arguments.get("source")) or is_sensitive_path(arguments.get("destination"))
    return False


def action_permission(action: str, arguments: dict | None = None) -> PermissionLevel:
    name = str(action or "").strip()
    arguments = dict(arguments or {})
    if _file_action_sensitive(name, arguments):
        return PermissionLevel.CRITICAL
    if name == "kill_process":
        return PermissionLevel.CRITICAL
    if name == "computer_action":
        sub = str(arguments.get("action") or "").strip().lower()
        return PermissionLevel.READ if sub in {"wait", "move"} else PermissionLevel.SYSTEM_ACTION
    if name == "app_control":
        sub = str(arguments.get("action") or "").strip().lower()
        return PermissionLevel.SAFE_ACTION if sub in {"focus", "minimize", "maximize", "restore"} else PermissionLevel.SYSTEM_ACTION
    if name == "power_action":
        sub = str(arguments.get("action") or "").strip().lower()
        return PermissionLevel.SAFE_ACTION if sub == "lock" else PermissionLevel.CRITICAL
    if name in READ_ACTIONS:
        return PermissionLevel.READ
    if name in SAFE_ACTIONS:
        return PermissionLevel.SAFE_ACTION
    if name in SYSTEM_ACTIONS:
        return PermissionLevel.SYSTEM_ACTION
    if name in CRITICAL_ACTIONS:
        return PermissionLevel.CRITICAL
    # Unknown remote commands fail closed at the highest level; DeviceExecutor
    # still rejects names that are not in its explicit handler table.
    return PermissionLevel.CRITICAL


def level_for_mode(mode: str) -> PermissionLevel | None:
    value = MODE_LEVELS.get(str(mode or "").strip().lower())
    if isinstance(value, PermissionLevel):
        return value
    return None


@dataclass(slots=True)
class RemotePolicyState:
    enabled: bool
    mode: str
    expires_at: float
    persistent: bool
    allow_power: bool
    allow_shell: bool
    armed_at: float

    @property
    def expired(self) -> bool:
        return bool(self.enabled and not self.persistent and self.expires_at > 0 and time.time() >= self.expires_at)

    @property
    def max_permission(self) -> PermissionLevel | None:
        if not self.enabled or self.expired:
            return None
        return level_for_mode(self.mode)


class RemoteAccessPolicy:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or POLICY_PATH).expanduser()

    def _read(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
        return raw if isinstance(raw, dict) else {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def state(self) -> RemotePolicyState:
        data = self._read()
        # Environment variables are deployment overrides, not a way to bypass a
        # local kill switch. A persisted local policy remains the normal source.
        mode = str(os.getenv("IRAS_REMOTE_ACCESS_MODE", data.get("mode", "off"))).strip().lower()
        if mode not in MODE_LEVELS:
            mode = "off"
        enabled = _truthy(os.getenv("IRAS_REMOTE_ACCESS_ENABLED", data.get("enabled", False)))
        persistent = _truthy(os.getenv("IRAS_REMOTE_ACCESS_PERSISTENT", data.get("persistent", False)))
        try:
            expires_at = float(data.get("expires_at") or 0)
        except (TypeError, ValueError):
            expires_at = 0.0
        if KILL_SWITCH_PATH.exists():
            enabled = False
        state = RemotePolicyState(
            enabled=bool(enabled and mode != "off"),
            mode=mode,
            expires_at=expires_at,
            persistent=persistent,
            allow_power=_truthy(os.getenv("IRAS_REMOTE_ALLOW_POWER", data.get("allow_power", False))),
            allow_shell=_truthy(os.getenv("IRAS_REMOTE_ALLOW_SHELL", data.get("allow_shell", False))),
            armed_at=float(data.get("armed_at") or 0),
        )
        if state.expired:
            return RemotePolicyState(False, "off", state.expires_at, False, state.allow_power, state.allow_shell, state.armed_at)
        return state

    def arm(
        self,
        mode: str = "control",
        *,
        minutes: int = 60,
        persistent: bool = False,
        allow_power: bool = False,
        allow_shell: bool = False,
    ) -> dict:
        mode = str(mode or "control").strip().lower()
        if mode not in {"read_only", "control", "full"}:
            raise ValueError("Remote mode must be read_only, control, or full.")
        if allow_shell and mode != "full":
            raise ValueError("Remote shell execution requires full mode.")
        if allow_power and mode != "full":
            raise ValueError("Remote restart/shutdown requires full mode.")
        minutes = max(5, min(int(minutes), 7 * 24 * 60))
        now = time.time()
        data = {
            "enabled": True,
            "mode": mode,
            "persistent": bool(persistent),
            "expires_at": 0 if persistent else now + minutes * 60,
            "allow_power": bool(allow_power),
            "allow_shell": bool(allow_shell),
            "armed_at": now,
        }
        self._write(data)
        try:
            KILL_SWITCH_PATH.unlink(missing_ok=True)
        except OSError:
            pass
        return self.status()

    def disarm(self, *, kill_switch: bool = False) -> dict:
        data = self._read()
        data.update({"enabled": False, "mode": "off", "persistent": False, "expires_at": 0})
        self._write(data)
        if kill_switch:
            KILL_SWITCH_PATH.parent.mkdir(parents=True, exist_ok=True)
            KILL_SWITCH_PATH.write_text("IRAS remote access disabled locally.\n", encoding="utf-8")
        return self.status()

    def authorize(
        self,
        action: str,
        arguments: dict | None = None,
        *,
        declared_permission: int | PermissionLevel | None = None,
    ) -> PermissionLevel:
        state = self.state()
        if not state.enabled:
            raise PermissionError(
                "IRAS remote access is locally disarmed. Run `iras remote arm ...` on the laptop first."
            )
        required = action_permission(action, arguments)
        if declared_permission is not None:
            try:
                declared = PermissionLevel(int(declared_permission))
            except (TypeError, ValueError):
                declared = required
            required = max(required, declared)
        maximum = state.max_permission
        if maximum is None or required > maximum:
            raise PermissionError(
                f"Remote action {action!r} requires {required.name}, but this laptop is armed only for {state.mode}."
            )
        if action == "power_action" and str((arguments or {}).get("action") or "").lower() != "lock" and not state.allow_power:
            raise PermissionError("Remote restart/shutdown is disabled by the laptop's local policy.")
        if action == "run_command" and not state.allow_shell:
            raise PermissionError("Remote command execution is disabled by the laptop's local policy.")
        return required

    def status(self) -> dict:
        state = self.state()
        remaining = None
        if state.enabled and not state.persistent and state.expires_at:
            remaining = max(0, int(state.expires_at - time.time()))
        return {
            "enabled": state.enabled,
            "mode": state.mode,
            "max_permission": state.max_permission.name if state.max_permission is not None else None,
            "persistent": state.persistent,
            "expires_at": state.expires_at or None,
            "remaining_seconds": remaining,
            "allow_power": state.allow_power,
            "allow_shell": state.allow_shell,
            "kill_switch": KILL_SWITCH_PATH.exists(),
            "policy_path": str(self.path),
        }
