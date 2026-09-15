from __future__ import annotations

import platform
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from iras import __version__
from iras.device_bridge.executor import DeviceExecutor


def main() -> None:
    print("=== IRAS v3.6.0 READ-ONLY REAL DEVICE SMOKE TEST ===")
    print("IRAS VERSION:", __version__)
    print("OS:", platform.system(), platform.release())

    if platform.system().lower() != "windows":
        print("RESULT: FAIL")
        raise SystemExit("This smoke test is intended for a real Windows device.")

    executor = DeviceExecutor()
    info = executor.system_info()
    status = executor.computer_status()
    observation = executor.computer_observe(
        vision="off",
        scope="foreground",
        max_elements=40,
    )

    foreground = observation.get("foreground") or {}
    title = str(foreground.get("title") or "")
    observation_id = str(observation.get("observation_id") or "")
    elements = observation.get("elements") or []

    assert __version__ == "3.6.0"
    assert isinstance(info, dict) and bool(info)
    assert isinstance(status, dict)
    assert observation_id
    assert isinstance(elements, list)

    print("SYSTEM INFO AVAILABLE:", True)
    print("COMPUTER STATUS AVAILABLE:", True)
    print("FOREGROUND TITLE:", title or "<empty>")
    print("FOREGROUND HWND:", foreground.get("hwnd"))
    print("OBSERVATION ID AVAILABLE:", bool(observation_id))
    print("UIA AVAILABLE:", observation.get("uia_available"))
    print("UIA ACTIONABLE:", observation.get("uia_actionable"))
    print("ELEMENT COUNT:", len(elements))
    print("VISION REQUESTED:", False)
    print("STATE-CHANGING ACTIONS EXECUTED:", False)
    print("ACTION REPLAY ALLOWED:", False)
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
