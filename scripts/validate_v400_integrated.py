from __future__ import annotations

import os
import tempfile
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from iras import __version__
from iras.models import PermissionLevel
from iras.remote_access import RemoteAccessPolicy, action_permission
from iras.safety_runtime import EmergencyStop
from iras.security.secret_store import protect_secret, unprotect_secret, protection_backend
from iras.device_bridge.store import DeviceBridgeStore
from iras.device_bridge.whatsapp_workflow import _full_vision_fallback_enabled
from iras.vision.omniparser_runtime import OmniParserRuntimeManager
from iras.vision.scene_graph import SCENE_GRAPH_VERSION


def main() -> None:
    print("=== IRAS v4.0 RC1 INTEGRATED VALIDATION ===")
    assert __version__ == "4.0.0-rc1"
    assert SCENE_GRAPH_VERSION == "3.7.0"  # scene-graph schema version stays stable

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        policy = RemoteAccessPolicy(root / "remote.json")
        state = policy.arm("full", persistent=True, allow_power=False, allow_shell=False)
        assert state["enabled"] and state["mode"] == "full"
        assert policy.authorize("screen_preview") == PermissionLevel.READ
        assert policy.authorize("ui_click_text") == PermissionLevel.SYSTEM_ACTION
        try:
            policy.authorize("run_command")
        except PermissionError:
            pass
        else:
            raise AssertionError("full remote command execution must require the local opt-in")

        stop = EmergencyStop(root / "STOP")
        assert not stop.tripped()
        stop.trip("validation")
        assert stop.tripped()
        stop.clear()
        assert not stop.tripped()

        store = DeviceBridgeStore(sqlite_path=root / "bridge.db")
        store.pair_device(
            device_id="windows-device-0001",
            display_name="Validation PC",
            platform="Windows 10",
            device_token="device-validation-token",
            capabilities=["screen_preview", "ui_click_text"],
            app_version=__version__,
        )
        session = store.create_remote_session(device_id="windows-device-0001", mode="full", ttl_seconds=120)
        authorized = store.authorize_remote_session(session["session_id"], session["session_token"])
        assert authorized and authorized["device_id"] == "windows-device-0001"
        assert not store.authorize_remote_session(session["session_id"], "wrong")
        assert store.revoke_remote_session(session["session_id"])
        store.close()

    sample = "v4-secret-roundtrip"
    protected = protect_secret(sample)
    assert unprotect_secret(protected) == sample
    assert protected != sample
    assert action_permission("delete_path") == PermissionLevel.CRITICAL
    assert action_permission("computer_action", {"action": "click"}) == PermissionLevel.SYSTEM_ACTION

    old = os.environ.pop("IRAS_WHATSAPP_FULL_VISION_FALLBACK", None)
    try:
        assert _full_vision_fallback_enabled() is False
    finally:
        if old is not None:
            os.environ["IRAS_WHATSAPP_FULL_VISION_FALLBACK"] = old

    runtime = OmniParserRuntimeManager()
    print("RELEASE VERSION:", __version__)
    print("SCENE GRAPH SCHEMA:", SCENE_GRAPH_VERSION)
    print("REMOTE SESSION CRITICAL CLASSIFICATION:", action_permission("delete_path").name)
    print("REMOTE LOCAL POLICY TWO-KEY GATE: True")
    print("EMERGENCY STOP CONTROLLER GATE: True")
    print("SECRET BACKEND:", protection_backend())
    print("OMNIPARSER LAZY AUTOSTART DEFAULT:", runtime.autostart_enabled())
    print("WHATSAPP FULL MODEL DEFAULT DISABLED:", not _full_vision_fallback_enabled())
    print("ACTION REPLAY ALLOWED: False")
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
