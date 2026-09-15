from __future__ import annotations

import tempfile
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from iras import __version__
from iras.device_bridge.adaptive_recovery import rank_recovery_routes
from iras.device_bridge.recovery_learning import RecoveryRoutePerformanceStore
from iras.device_bridge.recovery_runtime import select_recovery_route
from iras.device_bridge.workflow_memory import CrossAppWorkflowMemory


def verification():
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
    assert __version__ == "3.6.0"
    context = {
        "app": "whatsapp",
        "uia_actionable": True,
        "vision_scope": "none",
        "semantic": True,
    }

    with tempfile.TemporaryDirectory(prefix="iras-v360-") as tmp:
        store = RecoveryRoutePerformanceStore(Path(tmp) / "learning.json")
        for _ in range(8):
            store.record("uia_reground", success=True, context=context)
        for _ in range(3):
            store.record("uia_reground", success=False, context=context)

        output = verification()
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
        live_route_available = "uia_reground" in {
            item["route"] for item in ranked["rankings"]
        }

        memory = CrossAppWorkflowMemory()
        verified = memory.capture_verification(
            {"condition": "text_contains", "target": "Darkness"},
            {
                "status": "PASS",
                "condition": "text_contains",
                "semantic_goal_verified": True,
                "observation": {
                    "observation_id": "v360-whatsapp",
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

        cross_app_preserved = (
            verified.get("value") == "Darkness"
            and verified.get("source_app") == "whatsapp"
            and snapshot["current_app"] == "spotify"
            and any(item.get("value") == "Darkness" for item in snapshot["facts"])
        )

        assert stale_suppressed
        assert live_route_available
        assert cross_app_preserved
        assert snapshot["ephemeral"] is True
        assert snapshot["persisted"] is False
        assert snapshot["grants_tool_authorization"] is False
        assert ranked["current_state_authoritative"] is True
        assert ranked["action_replay_allowed"] is False
        assert snapshot["action_replay_allowed"] is False

        print("=== IRAS v3.6.0 INTEGRATED VALIDATION ===")
        print("RELEASE VERSION:", __version__)
        print("STALE CONTEXT STATUS:", health["status"])
        print("STALE LEARNED BOOST SUPPRESSED:", stale_suppressed)
        print("LIVE ROUTE STILL AVAILABLE:", live_route_available)
        print("VERIFIED HANDOFF FACT:", verified.get("value"))
        print("SOURCE APP:", verified.get("source_app"))
        print("DESTINATION APP:", snapshot["current_app"])
        print("CROSS-APP HANDOFF PRESERVED:", cross_app_preserved)
        print("WORKFLOW MEMORY EPHEMERAL:", snapshot["ephemeral"])
        print("WORKFLOW MEMORY PERSISTED:", snapshot["persisted"])
        print("GRANTS TOOL AUTHORIZATION:", snapshot["grants_tool_authorization"])
        print("CURRENT STATE AUTHORITATIVE:", ranked["current_state_authoritative"])
        print("ACTION REPLAY ALLOWED:", snapshot["action_replay_allowed"])
        print("RESULT: PASS")


if __name__ == "__main__":
    main()
