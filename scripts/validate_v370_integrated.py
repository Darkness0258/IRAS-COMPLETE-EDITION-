from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from iras import __version__
from iras.device_bridge.adaptive_recovery import rank_recovery_routes
from iras.device_bridge.recovery_learning import RecoveryRoutePerformanceStore
from iras.device_bridge.recovery_runtime import select_recovery_route
from iras.device_bridge.workflow_memory import CrossAppWorkflowMemory
from iras.device_bridge.intent import direct_device_intent
from iras.vision.omniparser_runtime import OmniParserRuntimeManager
from iras.vision.scene_graph import SCENE_GRAPH_VERSION, build_scene_graph


def _verification():
    return {
        "status": "FAIL",
        "condition": "text_contains",
        "scope": "foreground",
        "prior_foreground": {"title": "WhatsApp", "hwnd": 1},
        "observation": {
            "foreground": {"title": "WhatsApp", "hwnd": 1},
            "uia_actionable": True,
            "vision_scope": None,
        },
        "assessment": {
            "evidence_sources": ["uia"],
            "state_delta": {"foreground_changed": False},
        },
        "decision": {
            "action": "RETRY",
            "goal_sufficient": False,
            "failure_count": 1,
            "retry_budget_remaining": 1,
            "reason_codes": ["verification_not_satisfied"],
        },
    }


def main() -> None:
    assert __version__ == "3.7.0"
    assert SCENE_GRAPH_VERSION == "3.7.0"

    context = {
        "app": "whatsapp",
        "uia_actionable": True,
        "vision_scope": "none",
        "semantic": True,
    }

    with tempfile.TemporaryDirectory(prefix="iras-v370-") as tmp:
        store = RecoveryRoutePerformanceStore(Path(tmp) / "learning.json")
        for _ in range(8):
            store.record("uia_reground", success=True, context=context)
        for _ in range(3):
            store.record("uia_reground", success=False, context=context)

        output = _verification()
        args = {"condition": "text_contains", "scope": "foreground"}
        ranked = rank_recovery_routes(
            output,
            args,
            {
                "learned_route_priors": store.snapshot(),
                "learned_context_route_priors": store.context_snapshot(),
            },
            preferred_route=select_recovery_route(output, args),
        )
        uia = next(item for item in ranked["rankings"] if item["route"] == "uia_reground")
        health = uia["learning_calibration"]["prior_health"]
        stale_suppressed = (
            health["status"] == "quarantined"
            and uia["learning_calibration"]["combined_adjustment"] == 0.0
        )

        memory = CrossAppWorkflowMemory()
        verified = memory.capture_verification(
            {"condition": "text_contains", "target": "Darkness"},
            {
                "status": "PASS",
                "condition": "text_contains",
                "semantic_goal_verified": True,
                "observation": {
                    "observation_id": "v370-whatsapp",
                    "foreground": {"title": "WhatsApp", "hwnd": 10},
                },
                "decision": {
                    "action": "ACCEPT",
                    "goal_sufficient": True,
                    "failure_count": 0,
                    "retry_budget_remaining": 2,
                },
            },
        )
        memory.transition("Spotify", reason="validation_cross_app_handoff")
        snapshot = memory.snapshot()

        graph = build_scene_graph(
            [],
            [
                {
                    "source": "omniparser",
                    "label": "Darkness",
                    "name": "Darkness",
                    "role": "text",
                    "interactive": True,
                    "enabled": True,
                    "confidence": 0.91,
                    "rect": {"left": 100, "top": 100, "width": 120, "height": 30},
                }
            ],
            region={"left": 0, "top": 0, "width": 1920, "height": 1080},
            capture_sha256="validation",
        )
        visual = graph["elements"][0]

        whatsapp_fastpath = direct_device_intent(
            "Open WhatsApp, find Darkness and open that chat. Do not send anything. "
            "Verify visually that the chat header says Darkness."
        )

        old_url = os.environ.pop("IRAS_OMNIPARSER_URL", None)
        old_auto = os.environ.pop("IRAS_OMNIPARSER_AUTOSTART", None)
        try:
            default_lazy_autostart = (
                OmniParserRuntimeManager.autostart_enabled()
                and OmniParserRuntimeManager.base_url() == "http://127.0.0.1:8010"
            )
            r4_bridge_enabled = (
                OmniParserRuntimeManager.bridge_enabled()
                and OmniParserRuntimeManager.text_parse_url().endswith("/parse_text/")
            )
        finally:
            if old_url is not None:
                os.environ["IRAS_OMNIPARSER_URL"] = old_url
            if old_auto is not None:
                os.environ["IRAS_OMNIPARSER_AUTOSTART"] = old_auto

        assert stale_suppressed
        assert ranked["current_state_authoritative"] is True
        assert ranked["action_replay_allowed"] is False
        assert snapshot["action_replay_allowed"] is False
        assert snapshot["grants_tool_authorization"] is False
        assert verified.get("value") == "Darkness"
        assert graph["version"] == "3.7.0"
        assert visual["element_id"].startswith("vision:")
        assert visual["provenance"]["backend"] == "omniparser"
        assert default_lazy_autostart
        assert r4_bridge_enabled
        assert whatsapp_fastpath == {
            "tool": "device_whatsapp_open_chat",
            "arguments": {"contact": "Darkness"},
            "kind": "whatsapp_open_chat_verified",
        }

        print("=== IRAS v3.7.0 INTEGRATED VALIDATION ===")
        print("RELEASE VERSION:", __version__)
        print("STALE LEARNED BOOST SUPPRESSED:", stale_suppressed)
        print("CURRENT STATE AUTHORITATIVE:", ranked["current_state_authoritative"])
        print("ACTION REPLAY ALLOWED:", snapshot["action_replay_allowed"])
        print("CROSS-APP VERIFIED FACT:", verified.get("value"))
        print("MULTIMODAL SCENE GRAPH VERSION:", graph["version"])
        print("VISUAL STABLE ELEMENT ID:", visual["element_id"])
        print("VISUAL PROVENANCE:", visual["provenance"]["backend"])
        print("OMNIPARSER LAZY AUTOSTART DEFAULT:", default_lazy_autostart)
        print("R4 TEXT ROI BRIDGE ENABLED:", r4_bridge_enabled)
        print("WHATSAPP VISUAL FASTPATH:", whatsapp_fastpath["tool"])
        print("RESULT: PASS")


if __name__ == "__main__":
    main()
