from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from iras import __version__
from iras.device_bridge.intent import normalize_command
from iras.device_bridge.workflow_memory import safe_app_identity


MEDIA_APPS = {"spotify", "vlc"}
CONTINUATION_CUES = (
    "it",
    "there",
    "that app",
    "same app",
    "same task",
    "continue",
    "remember",
    "verified",
    "previous",
    "without reopening",
)


@dataclass
class AutonomySupervisor:
    """Small controller-level state used to make IRAS less brittle.

    This is deliberately not an unrestricted goal generator. It lets IRAS choose
    the next safe step *inside the user's goal*, resolve obvious conversational
    references from verified/session state, and avoid exposing model scratchpad.
    Permissions and device-tool safety remain authoritative.
    """

    current_app: str = "unknown"
    previous_app: str = "unknown"
    last_media_app: str = ""
    last_device_tool: str = ""
    last_verified_target: str = ""
    turn_index: int = 0
    recent_failures: list[str] = field(default_factory=list)

    def begin_turn(self) -> None:
        self.turn_index += 1

    def note_tool_result(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        payload: dict[str, Any] | None,
    ) -> None:
        args = arguments if isinstance(arguments, dict) else {}
        data = payload if isinstance(payload, dict) else {}
        ok = bool(data.get("ok"))
        output = data.get("output") if isinstance(data.get("output"), dict) else {}

        self.last_device_tool = str(name or "")

        if not ok:
            error = str(data.get("error") or "").strip()
            if error:
                self.recent_failures.append(error[:500])
                self.recent_failures = self.recent_failures[-3:]
            return

        app = ""
        if name in {
            "device_open_app",
            "device_app_control",
            "device_interact_app",
            "device_observe_ui",
            "device_semantic_action",
        }:
            app = str(args.get("app") or output.get("app") or "")
        elif name in {"device_spotify_play", "device_spotify_search"}:
            app = "spotify"
        elif name == "device_media_control":
            app = str(args.get("app") or output.get("target_app") or self.last_media_app)

        foreground = output.get("foreground") if isinstance(output.get("foreground"), dict) else {}
        if foreground.get("title"):
            fg_app = safe_app_identity(foreground.get("title"))
            if fg_app != "unknown":
                app = fg_app

        normalized = safe_app_identity(app)
        if normalized != "unknown":
            if normalized != self.current_app:
                self.previous_app = self.current_app
                self.current_app = normalized
            if normalized in MEDIA_APPS:
                self.last_media_app = normalized

        if name == "device_computer_verify":
            decision = output.get("decision") if isinstance(output.get("decision"), dict) else {}
            if bool(output.get("semantic_goal_verified")) or (
                str(decision.get("action") or "").upper() == "ACCEPT"
                and bool(decision.get("goal_sufficient"))
            ):
                target = args.get("target") or output.get("target")
                if target not in (None, ""):
                    self.last_verified_target = str(target)[:800]

    def contextual_direct_action(self, user_text: str) -> dict[str, Any] | None:
        """Resolve simple deictic media follow-ups from trusted session state."""
        command = normalize_command(user_text)
        lower = " ".join(command.lower().split())

        app = self.current_app
        if app not in MEDIA_APPS:
            app = self.last_media_app
        if app not in MEDIA_APPS:
            return None

        patterns = (
            (
                r"^(?:now\s+)?(?:play|resume|continue)(?:\s+(?:the\s+)?(?:music|song|track|it|this|that))?(?:\s+in\s+it)?$",
                "play",
            ),
            (
                r"^(?:now\s+)?(?:pause|hold)(?:\s+(?:the\s+)?(?:music|song|track|it|this|that))?(?:\s+in\s+it)?$",
                "pause",
            ),
            (
                r"^(?:now\s+)?(?:next|skip)(?:\s+(?:the\s+)?(?:song|track|it))?(?:\s+in\s+it)?$",
                "next",
            ),
            (
                r"^(?:now\s+)?(?:previous|prev|back)(?:\s+(?:the\s+)?(?:song|track|it))?(?:\s+in\s+it)?$",
                "previous",
            ),
            (
                r"^(?:now\s+)?stop(?:\s+(?:the\s+)?(?:music|song|track|it))?(?:\s+in\s+it)?$",
                "stop",
            ),
        )
        for pattern, action in patterns:
            if re.match(pattern, lower, flags=re.IGNORECASE):
                return {
                    "tool": "device_media_control",
                    "arguments": {"command": action, "app": app},
                    "kind": "contextual_media_control",
                }
        return None

    def should_use_workflow_memory(self, user_text: str) -> bool:
        lower = " ".join(str(user_text or "").lower().split())
        return any(cue in lower for cue in CONTINUATION_CUES)

    def system_message(self) -> str:
        return (
            "IRAS AUTONOMY SUPERVISOR: runtime_version="
            f"{__version__!r}; current_app={self.current_app!r}; "
            f"previous_app={self.previous_app!r}; last_media_app={self.last_media_app!r}; "
            f"last_verified_target={self.last_verified_target!r}. "
            "Within the user's stated goal, choose the next smallest safe and reversible step yourself. "
            "Do not ask the user to choose between safe approaches when a read-only observation can resolve the ambiguity. "
            "Prefer live state over assumptions, specialized tools over generic actions, and verification over confidence. "
            "You may adapt after failures, but never invent a new external goal, bypass permissions, or replay a failed state-changing action automatically. "
            "Keep private deliberation private: do not output scratchpad, hidden plans, or self-talk such as 'let me try'/'I need to'."
        )


def local_identity_reply(user_text: str) -> str | None:
    """Answer basic runtime identity/version queries without spending an LLM call."""
    q = " ".join(str(user_text or "").strip().lower().split())
    patterns = (
        r"^(?:what(?:'s| is)\s+)?(?:your|the|current)\s+(?:iras\s+)?version\??$",
        r"^what\s+version\s+(?:are\s+you|is\s+iras)(?:\s+running)?\??$",
        r"^iras\s+version\??$",
        r"^version\??$",
    )
    if any(re.match(pattern, q, flags=re.IGNORECASE) for pattern in patterns):
        return f"IRAS {__version__}."
    return None


def looks_like_private_deliberation(text: str) -> bool:
    """Detect leaked planner scratchpad so the controller can request a clean turn."""
    value = str(text or "").strip()
    if len(value) < 140:
        return False
    lower = value.lower()
    markers = (
        "let me try",
        "i need to understand",
        "i need to search",
        "i need to check",
        "actually, looking",
        "actually, the user",
        "re-reading the request",
        "let me re-read",
        "let me check",
        "but first, let me",
        "hmm, but",
    )
    return sum(marker in lower for marker in markers) >= 1
