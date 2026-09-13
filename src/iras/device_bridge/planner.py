from __future__ import annotations

import re

from iras.device_bridge.intent import (
    direct_device_intent,
    normalize_command,
)


# The autonomous planner may choose only from this bounded device set.
# It deliberately does not expose run_shell, kill_process, registry/admin
# controls, arbitrary subprocess execution, or any permission bypass.
SAFE_DEVICE_PLANNER_TOOLS = (
    "device_list",
    "device_system_info",
    "device_detect_apps",
    "device_app_control",
    "device_open_app",
    "device_interact_app",
    "device_observe_ui",
    "device_semantic_action",
    "device_spotify_search",
    "device_spotify_play",
    "device_media_control",
    "device_open_url",
    "device_open_project",
    "device_list_files",
    "device_read_text",
    "device_git_status",
    "device_run_tests",
    "device_capture_screen",
)

INFORMATIONAL_PREFIX_RE = re.compile(
    r"^(?:"
    r"how\s+(?:do|can|could|would|should)\s+i\b|"
    r"how\s+to\b|"
    r"what\s+(?:is|are|does|do)\b|"
    r"why\b|"
    r"explain\b|"
    r"tell\s+me\s+how\b|"
    r"show\s+me\s+how\b|"
    r"teach\s+me\b"
    r")",
    flags=re.IGNORECASE,
)

DEVICE_ACTION_RE = re.compile(
    r"^(?:"
    r"open|launch|start|run|close|quit|exit|"
    r"focus|switch|bring|minimize|maximize|restore|"
    r"search|find|look|type|write|enter|press|click|"
    r"double\s+click|scroll|select|paste|navigate|go|"
    r"play|pause|resume|continue|stop|next|skip|"
    r"previous|prev|mute|unmute|increase|decrease|"
    r"read|list|show|check|capture|take|test"
    r")\b",
    flags=re.IGNORECASE,
)

DEVICE_HINT_RE = re.compile(
    r"\b(?:"
    r"pc|computer|laptop|desktop|windows|"
    r"app|application|program|window|browser|"
    r"file|folder|directory|project|repo|repository|"
    r"screen|screenshot|spotify|chrome|edge|firefox|"
    r"discord|telegram|whatsapp|vlc|notepad|"
    r"vs\s*code|vscode|visual\s+studio\s+code"
    r")\b",
    flags=re.IGNORECASE,
)

NON_DEVICE_OBJECT_RE = re.compile(
    r"^(?:"
    r"open\s+(?:a|an|my|the)?\s*bank\s+account\b|"
    r"open\s+(?:a|an|the)?\s*discussion\b|"
    r"open\s+(?:a|an|the)?\s*conversation\b|"
    r"start\s+(?:a|an|the)?\s*discussion\b"
    r")",
    flags=re.IGNORECASE,
)


def should_use_device_planner(
    text: str,
) -> bool:
    """
    Detect a likely real device task that the deterministic router did not
    understand. This is the bridge between rigid regex commands and model-led
    multi-step tool planning.
    """
    command = normalize_command(
        text
    ).strip()

    if not command:
        return False

    if INFORMATIONAL_PREFIX_RE.match(
        command
    ):
        return False

    if NON_DEVICE_OBJECT_RE.match(
        command
    ):
        return False

    # If the deterministic layer understands the command, it remains the
    # fast/reliable route and the planner is unnecessary.
    if direct_device_intent(
        command
    ):
        return False

    if DEVICE_HINT_RE.search(
        command
    ):
        return True

    if DEVICE_ACTION_RE.match(
        command
    ):
        return True

    # Compound continuation language is a strong signal for a task that may
    # need several tool calls, e.g. "open Discord and message Hamza".
    if re.search(
        r"\b(?:and\s+then|then|after\s+that)\b",
        command,
        flags=re.IGNORECASE,
    ):
        return True

    return False


def _clean_app_candidate(
    value: str,
) -> str:
    value = " ".join(
        str(value or "")
        .strip(" \t,.:;!?-")
        .split()
    )

    value = re.sub(
        r"\s+(?:app|application)$",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()

    return value


def extract_app_scope(
    text: str,
) -> list[str]:
    """
    Extract only app names explicitly named in the current turn.

    This is not used to decide what action to take. It is a safety scope used
    after the model chooses a tool so prior conversation context cannot cause
    it to operate a different GUI app.
    """
    command = normalize_command(
        text
    )

    found = []

    deterministic = direct_device_intent(
        command
    )

    if deterministic:
        app = (
            deterministic.get(
                "arguments",
                {},
            ).get(
                "app"
            )
        )

        if app:
            found.append(
                _clean_app_candidate(
                    app
                )
            )

    # Project/file/URL commands have their own specialized device tools and
    # should not be mistaken for application names.
    lower = command.lower()
    if re.match(
        r"^(?:open|launch|start)\s+(?:my\s+|the\s+)?"
        r"(?:project|file|folder|website|url)\b",
        lower,
    ):
        return found

    # If a known game-style request deliberately bypassed Spotify routing,
    # treat the title as the current app scope so the planner cannot choose an
    # unrelated GUI app from conversation history.
    game_match = re.match(
        r"^play\s+((?:gta|grand\s+theft\s+auto|valorant|fortnite|"
        r"minecraft|elden\s+ring|call\s+of\s+duty|cod\b|battlefield|"
        r"forza|need\s+for\s+speed|nfs\b|cyberpunk).*)$",
        command,
        flags=re.IGNORECASE,
    )

    if game_match:
        found.append(
            _clean_app_candidate(
                game_match.group(1)
            )
        )

    patterns = (
        # "open Discord and send..."
        r"^(?:open|launch|start|close|quit|exit|focus|minimize|maximize|restore)"
        r"\s+(?:the\s+)?(.+?)(?=\s+(?:and|then)\b|$)",
        # "... in Discord", "... on VLC", "... into Notepad"
        r"\s+(?:in|into|on)\s+([A-Za-z0-9][A-Za-z0-9 .+_-]{0,80})$",
        # "switch to Discord"
        r"^switch\s+to\s+(.+?)(?=\s+(?:and|then)\b|$)",
        # "bring Discord to front"
        r"^bring\s+(.+?)\s+to\s+front$",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            command,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        candidate = _clean_app_candidate(
            match.group(1)
        )

        if (
            candidate
            and candidate.lower()
            not in {
                "my pc",
                "my computer",
                "my laptop",
                "my desktop",
                "the pc",
                "the computer",
                "the laptop",
            }
            and candidate.lower()
            not in {
                item.lower()
                for item in found
            }
        ):
            found.append(
                candidate
            )

    return found


def planner_system_nudge(
    user_text: str,
    app_scope: list[str] | None = None,
) -> str:
    scope_text = ""

    if app_scope:
        scope_text = (
            " The current turn explicitly names only these GUI app targets: "
            + ", ".join(app_scope)
            + ". Do not operate a different GUI app."
        )

    return (
        "BOUNDED AUTONOMOUS DEVICE PLANNER MODE: "
        "The current request appears to require a real computer action that "
        "the deterministic command router did not fully understand. Infer the "
        "user's goal and privately plan the smallest safe sequence of supplied "
        "tools needed to complete it. You may make multiple tool calls and "
        "adapt after each real tool result. Do not reveal hidden chain-of-"
        "thought; report only useful actions/results. Prefer specialized tools "
        "over generic UI automation. If an installed app name is uncertain, "
        "use device_detect_apps first. For a normal installed GUI app, use "
        "device_open_app/device_app_control and then device_interact_app when "
        "keyboard or mouse actions are actually expressible with that tool. "
        "For unfamiliar GUIs, call device_observe_ui before clicking. "
        "Reason only from returned visible UI elements. Prefer "
        "device_semantic_action for buttons, fields, tabs, menus and "
        "list items, then re-observe and adapt after meaningful actions. "
        "For URLs/websites prefer device_open_url. For files/projects use the "
        "file/project tools. Never invent a click coordinate or claim you saw "
        "screen content that no tool returned. If a tool fails, inspect the "
        "error and try a safe alternative when one exists. If the requested "
        "operation cannot be completed with the supplied bounded tools, say "
        "exactly what capability is missing instead of fabricating success."
        + scope_text
    )
