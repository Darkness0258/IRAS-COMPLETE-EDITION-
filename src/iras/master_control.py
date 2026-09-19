from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import time
from typing import Any

from iras.models import ApprovalRequest, PermissionLevel
from iras.remote_access import RemoteAccessPolicy
from iras.safety_runtime import EmergencyStop
from iras.security.permissions import PermissionDenied, PermissionEngine


MASTER_CONTROL_PATH = Path.home() / ".iras" / "master_control.json"


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def emergency_execution_limits() -> dict[str, int | str | bool]:
    """High-capacity execution profile used only while local Master Control is armed.

    The profile intentionally removes ordinary small workflow budgets without
    creating a truly infinite loop. A large owner-configurable watchdog remains
    so a broken provider/tool cannot consume CPU, quota, or disk forever.
    """
    return {
        "mode": "emergency_adaptive",
        "agent_steps": _env_int("IRAS_MASTER_AGENT_STEPS", 256, 32, 4096),
        "runtime_watchdog_seconds": _env_int("IRAS_MASTER_RUNTIME_SECONDS", 21600, 300, 86400),
        "parallel_tasks": _env_int("IRAS_MASTER_PARALLEL_TASKS", 128, 12, 512),
        "orchestration_tasks": _env_int("IRAS_MASTER_ORCHESTRATION_TASKS", 128, 20, 512),
        "active_runs": _env_int("IRAS_MASTER_ACTIVE_RUNS", 32, 4, 128),
        "provider_wait_seconds": _env_int("IRAS_MASTER_PROVIDER_WAIT_SECONDS", 86400, 900, 86400),
        "recovery_attempts": _env_int("IRAS_MASTER_RECOVERY_ATTEMPTS", 24, 4, 128),
        "ordinary_refusal_policy": "no_ordinary_refusal_continue_until_complete_or_concrete_blocker",
    }


def active_master_execution_limits() -> dict[str, int | str | bool]:
    """Return the emergency profile only for a locally armed autonomous Master session."""
    try:
        status = MasterControl().status()
    except Exception:
        status = {}
    limits = emergency_execution_limits()
    limits["active"] = bool(status.get("enabled") and status.get("autonomous"))
    return limits


def is_master_remote_session(session: dict[str, Any] | None) -> bool:
    if not isinstance(session, dict):
        return False
    scopes = {str(item).strip().lower() for item in (session.get("scopes") or [])}
    try:
        level = int(session.get("max_permission") or 0)
    except (TypeError, ValueError):
        level = 0
    return "master" in scopes and level >= int(PermissionLevel.CRITICAL)


def master_execution_limits_for_context(context: dict[str, Any] | None = None) -> dict[str, int | str | bool]:
    limits = active_master_execution_limits()
    if limits.get("active"):
        return limits
    context = context if isinstance(context, dict) else {}
    if is_master_remote_session(context.get("remote_session")):
        limits = emergency_execution_limits()
        limits["active"] = True
        limits["source"] = "verified_remote_master_session"
        return limits
    return limits


@dataclass(slots=True)
class MasterState:
    enabled: bool = False
    armed_at: float = 0.0
    expires_at: float = 0.0
    persistent: bool = False
    allow_power: bool = True
    allow_shell: bool = True
    autonomous: bool = True
    source: str = "local"
    previous_remote: dict[str, Any] | None = None

    @property
    def expired(self) -> bool:
        return bool(self.enabled and not self.persistent and self.expires_at > 0 and time.time() >= self.expires_at)


class MasterControl:
    """Local owner-controlled elevation for IRAS.

    Master Control is deliberately rooted on the Windows machine.  Cloud, web
    and mobile clients may *use* a full remote session while Master Control is
    active, but they cannot turn it on by themselves.  The emergency stop and
    Windows/OS security boundaries are never bypassed.
    """

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        remote_policy: RemoteAccessPolicy | None = None,
        emergency_stop: EmergencyStop | None = None,
    ):
        self.path = Path(path or MASTER_CONTROL_PATH).expanduser()
        self.remote_policy = remote_policy or RemoteAccessPolicy()
        self.emergency_stop = emergency_stop or EmergencyStop()

    def _read_raw(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            value = {}
        return value if isinstance(value, dict) else {}

    def _write(self, state: MasterState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(state), indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @staticmethod
    def _state_from(data: dict[str, Any]) -> MasterState:
        return MasterState(
            enabled=bool(data.get("enabled", False)),
            armed_at=float(data.get("armed_at") or 0),
            expires_at=float(data.get("expires_at") or 0),
            persistent=bool(data.get("persistent", False)),
            allow_power=bool(data.get("allow_power", True)),
            allow_shell=bool(data.get("allow_shell", True)),
            autonomous=bool(data.get("autonomous", True)),
            source=str(data.get("source") or "local")[:80],
            previous_remote=data.get("previous_remote") if isinstance(data.get("previous_remote"), dict) else None,
        )

    def _restore_remote(self, previous: dict[str, Any] | None) -> None:
        if not previous or not previous.get("enabled"):
            self.remote_policy.disarm(kill_switch=False)
            return
        mode = str(previous.get("mode") or "control")
        persistent = bool(previous.get("persistent"))
        remaining = previous.get("remaining_seconds")
        try:
            minutes = max(5, int((int(remaining or 3600) + 59) // 60))
        except Exception:
            minutes = 60
        self.remote_policy.arm(
            mode,
            minutes=minutes,
            persistent=persistent,
            allow_power=bool(previous.get("allow_power", False)),
            allow_shell=bool(previous.get("allow_shell", False)),
        )

    def state(self) -> MasterState:
        state = self._state_from(self._read_raw())
        if state.expired:
            self.disable(restore_remote=True, source="expiry")
            return MasterState(enabled=False, source="expiry")
        if self.emergency_stop.tripped() and state.enabled:
            # Emergency stop wins over elevation. Keep the file disabled and
            # locally disarm Remote so no later process can inherit a stale grant.
            self.disable(restore_remote=False, source="emergency_stop")
            try:
                self.remote_policy.disarm(kill_switch=False)
            except Exception:
                pass
            return MasterState(enabled=False, source="emergency_stop")
        return state

    @staticmethod
    def _bridge_roots() -> list[str]:
        path = Path.home() / ".iras-device-bridge.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            roots = data.get("allowed_roots") or []
            return [str(item) for item in roots if str(item).strip()]
        except Exception:
            return []

    def status(self) -> dict[str, Any]:
        state = self.state()
        remaining = None
        if state.enabled and not state.persistent and state.expires_at:
            remaining = max(0, int(state.expires_at - time.time()))
        remote = self.remote_policy.status()
        roots = self._bridge_roots()
        return {
            "enabled": state.enabled,
            "armed_at": state.armed_at or None,
            "expires_at": state.expires_at or None,
            "remaining_seconds": remaining,
            "persistent": state.persistent,
            "allow_power": state.allow_power,
            "allow_shell": state.allow_shell,
            "autonomous": state.autonomous,
            "source": state.source,
            "permission_level": "CRITICAL" if state.enabled else None,
            "remote_mode": remote.get("mode"),
            "remote_enabled": bool(remote.get("enabled")),
            "emergency_stop": bool(self.emergency_stop.tripped()),
            "filesystem_roots": roots,
            "execution_profile": (
                emergency_execution_limits()
                if state.enabled and state.autonomous
                else {"mode": "normal", "active": False}
            ),
            "path": str(self.path),
        }

    def enable(
        self,
        *,
        minutes: int = 30,
        persistent: bool = False,
        allow_power: bool = True,
        allow_shell: bool = True,
        autonomous: bool = True,
        source: str = "local",
    ) -> dict[str, Any]:
        self.emergency_stop.assert_clear()
        minutes = max(5, min(int(minutes), 12 * 60))
        now = time.time()
        previous = self.remote_policy.status()
        state = MasterState(
            enabled=True,
            armed_at=now,
            expires_at=0 if persistent else now + minutes * 60,
            persistent=bool(persistent),
            allow_power=bool(allow_power),
            allow_shell=bool(allow_shell),
            autonomous=bool(autonomous),
            source=str(source or "local")[:80],
            previous_remote=previous,
        )
        # The existing RemoteAccessPolicy remains the enforcement boundary for
        # outbound cloud/device work. Master Control simply arms its strongest
        # supported mode for the same bounded lifetime.
        self.remote_policy.arm(
            "full",
            minutes=minutes,
            persistent=bool(persistent),
            allow_power=bool(allow_power),
            allow_shell=bool(allow_shell),
        )
        self._write(state)
        return self.status()

    def disable(
        self,
        *,
        restore_remote: bool = True,
        source: str = "local",
    ) -> dict[str, Any]:
        current = self._state_from(self._read_raw())
        previous = current.previous_remote
        disabled = MasterState(enabled=False, source=str(source or "local")[:80])
        self._write(disabled)
        if restore_remote:
            try:
                self._restore_remote(previous)
            except Exception:
                # Disabling elevation must never fail because restoring a prior
                # convenience policy failed. Falling back to disarmed is safer.
                try:
                    self.remote_policy.disarm(kill_switch=False)
                except Exception:
                    pass
        return self.status()


class MasterPermissionEngine(PermissionEngine):
    """PermissionEngine that honors a locally armed Master Control grant."""

    def __init__(self, *args, master_control: MasterControl | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.master_control = master_control or MasterControl()

    def authorize(self, request: ApprovalRequest) -> None:
        state = self.master_control.state()
        if state.enabled:
            if self.master_control.emergency_stop.tripped():
                raise PermissionDenied("IRAS emergency stop is active.")
            if request.permission <= self.hard_cap:
                return
        super().authorize(request)
