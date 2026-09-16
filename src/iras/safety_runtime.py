from __future__ import annotations

"""Controller-level emergency stop shared by local and remote execution."""

from pathlib import Path
import os
import time


DEFAULT_STOP_PATH = Path.home() / ".iras" / "EMERGENCY_STOP"


class EmergencyStop:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or DEFAULT_STOP_PATH).expanduser()

    def tripped(self) -> bool:
        return self.path.exists()

    def assert_clear(self) -> None:
        if self.tripped():
            raise PermissionError(
                "IRAS emergency stop is active. Clear it locally before any further computer action."
            )

    def trip(self, reason: str = "user_requested") -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            f"IRAS emergency stop\nreason={str(reason)[:240]}\nat={time.time()}\n",
            encoding="utf-8",
        )
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        return self.status()

    def clear(self) -> dict:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError(f"Could not clear IRAS emergency stop: {exc}") from exc
        return self.status()

    def status(self) -> dict:
        return {"tripped": self.tripped(), "path": str(self.path)}
