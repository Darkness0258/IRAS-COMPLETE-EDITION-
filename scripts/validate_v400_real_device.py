from __future__ import annotations

import platform
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from iras import __version__
from iras.device_bridge.executor import DeviceExecutor
from iras.remote_access import RemoteAccessPolicy
from iras.safety_runtime import EmergencyStop
from iras.voice.stt import Listener
from iras.vision.omniparser_runtime import OmniParserRuntimeManager


def main() -> None:
    print("=== IRAS v4.0 RC1 READ-ONLY REAL DEVICE SMOKE TEST ===")
    print("VERSION:", __version__)
    print("PLATFORM:", platform.platform())
    if platform.system().lower() != "windows":
        print("RESULT: NOT RUN (Windows real-device acceptance requires Windows)")
        raise SystemExit(2)
    executor = DeviceExecutor()
    info = executor.system_info()
    print("SYSTEM INFO: PASS", info.get("platform") or info.get("os") or "")
    processes = executor.list_processes(limit=5)
    print("PROCESS LIST: PASS", len(processes.get("processes") or []))
    print("REMOTE POLICY:", RemoteAccessPolicy().status())
    print("EMERGENCY STOP:", EmergencyStop().status())
    print("MICROPHONE:", Listener.microphone_status())
    vision = OmniParserRuntimeManager().status()
    print("VISION STATUS:", {k: vision.get(k) for k in ("status", "ready", "base_url", "bridge_enabled")})
    print("HOME EXISTS:", Path.home().exists())
    print("RESULT: PASS (read-only; no click/type/send/delete/power action executed)")


if __name__ == "__main__":
    main()
