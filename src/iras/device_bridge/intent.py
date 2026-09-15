from __future__ import annotations

import re


WAKE_PREFIX_RE = re.compile(
    r"^(?:(?:hey|hi|hello)\s+)?(?:iras|iris|eris|eras)\s*[,.:;!?-]*\s*",
    flags=re.IGNORECASE,
)

POLITE_PREFIXES = (
    r"please\s+",
    r"can\s+you\s+",
    r"could\s+you\s+",
    r"would\s+you\s+",
    r"will\s+you\s+",
    r"i\s+want\s+you\s+to\s+",
    r"i\s+need\s+you\s+to\s+",
)

RETRY_PHRASES = {
    "again",
    "do it again",
    "do that again",
    "retry",
    "retry it",
    "retry that",
    "try again",
    "try it again",
    "try that again",
    "same again",
    "same song again",
    "play it again",
    "play that again",
    "play the same song again",
    "repeat that song",
}

MEDIA_CONTROL_PATTERNS = (
    (r"^(?:play|resume|continue)(?:\s+(?:the\s+)?(?:song|music|track))?$", "play"),
    (r"^(?:pause|hold)(?:\s+(?:the\s+)?(?:song|music|track))?$", "pause"),
    (r"^(?:next|skip)(?:\s+(?:the\s+)?(?:song|track))?$", "next"),
    (r"^(?:previous|prev|back)(?:\s+(?:to\s+)?(?:the\s+)?(?:song|track))?$", "previous"),
    (r"^stop(?:\s+(?:the\s+)?(?:song|music|track))?$", "stop"),
    (r"^(?:mute|mute\s+the\s+music|mute\s+spotify)$", "mute"),
    (r"^(?:unmute|unmute\s+the\s+music|unmute\s+spotify)$", "unmute"),
    (r"^(?:volume\s+up|turn\s+it\s+up|turn\s+the\s+volume\s+up|louder|increase\s+volume)$", "volume_up"),
    (r"^(?:volume\s+down|turn\s+it\s+down|turn\s+the\s+volume\s+down|quieter|decrease\s+volume|lower\s+volume)$", "volume_down"),
    (r"^(?:shuffle|shuffle\s+music|shuffle\s+spotify|toggle\s+shuffle|turn\s+shuffle\s+(?:on|off))$", "shuffle_toggle"),
    (r"^(?:repeat|repeat\s+mode|toggle\s+repeat|turn\s+repeat\s+(?:on|off))$", "repeat_toggle"),
    (r"^(?:like|like\s+this|like\s+this\s+song|save\s+this\s+song|add\s+this\s+song\s+to\s+library)$", "like_toggle"),
    (r"^(?:unlike|unlike\s+this|unlike\s+this\s+song|remove\s+this\s+song\s+from\s+library)$", "like_toggle"),
    (r"^(?:open|show|go\s+to)\s+(?:the\s+)?queue$", "open_queue"),
    (r"^(?:open|show|go\s+to)\s+(?:my\s+)?liked\s+songs$", "open_liked_songs"),
    (r"^(?:open|show|go\s+to)\s+(?:the\s+)?now\s+playing(?:\s+view)?$", "open_now_playing"),
    (r"^(?:play\s*\/\s*pause|toggle\s+playback)$", "play_pause"),
)

SEARCH_PATTERNS = (
    r"^search\s+spotify\s+(?:for\s+)?(.+)$",
    r"^spotify\s+search\s+(?:for\s+)?(.+)$",
    r"^search\s+(?:for\s+)?(.+?)\s+(?:on|in)\s+spotify$",
    r"^find\s+(.+?)\s+(?:on|in)\s+spotify$",
    r"^look\s+(?:up|for)\s+(.+?)\s+(?:on|in)\s+spotify$",
)

PLAY_PATTERNS = (
    r"^(?:open\s+spotify\s+(?:and\s+)?)?play\s+(?:me\s+)?(.+?)(?:\s+on\s+spotify)?$",
    r"^spotify\s+(?:play|start)\s+(.+)$",
    r"^(?:put\s+on|put)\s+(.+?)(?:\s+on\s+spotify)?$",
    r"^listen\s+to\s+(.+?)(?:\s+on\s+spotify)?$",
    r"^start\s+playing\s+(.+?)(?:\s+on\s+spotify)?$",
)

GENERIC_QUERY_WORDS = {
    "it",
    "that",
    "this",
    "the song",
    "song",
    "the music",
    "music",
    "the track",
    "track",
    "something",
    "anything",
}

NON_SPOTIFY_DESTINATIONS = (
    " on youtube",
    " in youtube",
    " on vlc",
    " in vlc",
    " in chrome",
    " on chrome",
    " on netflix",
)

NON_MUSIC_PLAY_PREFIXES = (
    "game ",
    "video ",
    "movie ",
    "episode ",
)

GENERIC_APP_NOUNS = {
    "app",
    "application",
    "project",
    "file",
    "folder",
    "website",
    "url",
    "queue",
    "liked songs",
    "now playing",
}

BROWSER_NAMES = {
    "chrome",
    "google chrome",
    "edge",
    "microsoft edge",
    "firefox",
    "mozilla firefox",
    "brave",
    "brave browser",
    "opera",
}


def normalize_command(text: str) -> str:
    value = " ".join(
        str(text or "")
        .strip()
        .split()
    )

    value = WAKE_PREFIX_RE.sub(
        "",
        value,
        count=1,
    )

    changed = True

    while changed:
        changed = False

        for pattern in POLITE_PREFIXES:
            new_value = re.sub(
                "^" + pattern,
                "",
                value,
                count=1,
                flags=re.IGNORECASE,
            )

            if new_value != value:
                value = new_value.strip()
                changed = True

    return value.strip()


def _clean_query(value: str) -> str:
    query = " ".join(
        str(value or "")
        .strip(" \t,.:;!?-")
        .split()
    )

    query = re.sub(
        r"\s+(?:please|for\s+me)$",
        "",
        query,
        flags=re.IGNORECASE,
    ).strip()

    return query


def _strip_verification_suffix(value: str) -> str:
    """Remove an explicit follow-up verification clause from a command.

    The verifier belongs to the closed-loop planner; it must not leak into a
    Spotify search/play query or prevent a deterministic media-control parse.
    """
    text = str(value or "").strip()
    if not text:
        return text

    parts = re.split(
        r"(?:\s*[,;]\s*|\s+)(?:(?:and\s+)?then\s+|and\s+)?"
        r"(?:verify|check|confirm)\b",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    return parts[0].strip(" \t,;.-")


def _clean_spotify_query(value: str) -> str:
    query = _clean_query(
        _strip_verification_suffix(value)
    )
    query = re.sub(
        r"\s+(?:on|in)\s+spotify$",
        "",
        query,
        flags=re.IGNORECASE,
    ).strip()
    return query


def _normalize_voice_music_form(command: str) -> str:
    match = re.match(
        r"^(?:yeah|yah|ya)\s+(.+\b(?:song|track|music|playlist|album)\b.*)$",
        command,
        flags=re.IGNORECASE,
    )

    if match:
        return "play " + match.group(1)

    return command


def is_retry_phrase(text: str) -> bool:
    return normalize_command(text).lower() in RETRY_PHRASES


def media_control_from_text(text: str) -> str | None:
    command = normalize_command(text).lower()

    for pattern, action in MEDIA_CONTROL_PATTERNS:
        if re.match(pattern, command, flags=re.IGNORECASE):
            return action

    return None


def media_control_request_from_text(text: str) -> dict | None:
    command = _strip_verification_suffix(normalize_command(text))
    lower = command.lower()

    # A request such as "play video on YouTube" is a content/navigation
    # request, not a transport-resume command. Preserve it for browser/video
    # routing while still allowing pause/stop/resume of existing media.
    if re.match(
        r"^(?:play|start)\s+(?:the\s+)?(?:video|movie|episode)"
        r"\s+(?:on|in)\s+(?:youtube|netflix|prime\s+video)\b",
        lower,
    ):
        return None

    exact = media_control_from_text(command)

    if exact:
        return {
            "command": exact,
        }

    spotify_transport = re.match(
        r"^(pause|hold|resume|continue|stop|next|skip|previous|prev|mute|unmute)"
        r"\s+(?:the\s+)?spotify$",
        command,
        flags=re.IGNORECASE,
    )
    if spotify_transport:
        verb = spotify_transport.group(1).lower()
        mapping = {
            "hold": "pause",
            "resume": "play",
            "continue": "play",
            "skip": "next",
            "prev": "previous",
        }
        return {
            "command": mapping.get(verb, verb),
            "app": "spotify",
        }

    target_patterns = (
        (
            r"^(pause|hold|resume|continue|stop|next|skip|previous|prev|mute|unmute)"
            r"(?:\s+(?:the\s+)?(?:song|music|track|video))?"
            r"\s+(?:on|in)\s+(.+)$"
        ),
    )

    for pattern in target_patterns:
        match = re.match(
            pattern,
            command,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        verb = match.group(1).lower()
        app = _clean_query(match.group(2))
        mapping = {
            "hold": "pause",
            "resume": "play",
            "continue": "play",
            "skip": "next",
            "prev": "previous",
        }

        return {
            "command": mapping.get(verb, verb),
            "app": app,
        }

    match = re.match(
        r"^(?:play|resume|continue)\s+(?:the\s+)?(?:song|music|track|video)"
        r"\s+(?:on|in)\s+(.+)$",
        command,
        flags=re.IGNORECASE,
    )

    if match:
        return {
            "command": "play",
            "app": _clean_query(match.group(1)),
        }

    match = re.match(
        r"^(volume\s+up|volume\s+down|turn\s+it\s+up|turn\s+it\s+down)"
        r"\s+(?:on|in)\s+(.+)$",
        command,
        flags=re.IGNORECASE,
    )

    if match:
        action = match.group(1).lower()
        action = {
            "turn it up": "volume_up",
            "turn it down": "volume_down",
            "volume up": "volume_up",
            "volume down": "volume_down",
        }[action]

        return {
            "command": action,
            "app": _clean_query(match.group(2)),
        }

    return None


def spotify_search_query_from_text(
    text: str,
    *,
    spotify_context: bool = False,
) -> str | None:
    command = _normalize_voice_music_form(
        _strip_verification_suffix(normalize_command(text))
    )

    for pattern in SEARCH_PATTERNS:
        match = re.match(
            pattern,
            command,
            flags=re.IGNORECASE,
        )

        if match:
            query = _clean_spotify_query(
                match.group(1)
            )
            return query if query else None

    # Natural follow-up inside an established Spotify context:
    # "search another song", "find Atif Aslam", "look up Heeriye".
    # Commands naming another target with "in/on" are left to the planner.
    if spotify_context:
        lower = command.lower()

        if (
            " in " not in lower
            and " on " not in lower
        ):
            match = re.match(
                r"^(?:search|find|look\s+up|look\s+for)"
                r"(?:\s+for)?\s+(.+)$",
                command,
                flags=re.IGNORECASE,
            )

            if match:
                query = _clean_spotify_query(
                    match.group(1)
                )

                if query:
                    return query

    return None


def spotify_query_from_text(
    text: str,
    *,
    spotify_context: bool = False,
) -> str | None:
    command = _normalize_voice_music_form(
        _strip_verification_suffix(normalize_command(text))
    )
    lower = command.lower()

    if any(destination in lower for destination in NON_SPOTIFY_DESTINATIONS):
        return None

    explicit_spotify = "spotify" in lower
    query = None

    for pattern in PLAY_PATTERNS:
        match = re.match(pattern, command, flags=re.IGNORECASE)

        if match:
            query = _clean_spotify_query(match.group(1))
            break

    if not query:
        return None

    query_lower = query.lower()

    if query_lower in GENERIC_QUERY_WORDS:
        return None

    obvious_non_music = (
        "gta",
        "grand theft auto",
        "valorant",
        "fortnite",
        "minecraft",
        "elden ring",
        "call of duty",
        "cod ",
        "battlefield",
        "forza",
        "need for speed",
        "nfs ",
        "cyberpunk",
    )

    if (
        not explicit_spotify
        and not spotify_context
        and any(
            query_lower == name
            or query_lower.startswith(name + " ")
            for name in obvious_non_music
        )
    ):
        return None

    if (
        not explicit_spotify
        and not spotify_context
        and any(
            query_lower.startswith(prefix)
            for prefix in NON_MUSIC_PLAY_PREFIXES
        )
    ):
        return None

    return query


def _open_spotify_intent(text: str) -> bool:
    command = normalize_command(text).lower()

    return bool(
        re.match(
            r"^(?:open|launch|start)\s+(?:the\s+)?spotify(?:\s+app)?$",
            command,
        )
    )


def detect_apps_intent(text: str) -> dict | None:
    command = normalize_command(text)
    lower = command.lower()

    if lower in {
        "list apps",
        "list installed apps",
        "what apps are installed",
        "what applications are installed",
        "detect apps",
        "detect installed apps",
        "show installed apps",
        "show running apps",
        "what apps are running",
    }:
        return {
            "tool": "device_detect_apps",
            "arguments": {
                "query": "",
            },
            "kind": "app_detect",
        }

    match = re.match(
        r"^(?:find|detect|look\s+for)\s+(?:the\s+)?(?:app|application)\s+(.+)$",
        command,
        flags=re.IGNORECASE,
    )

    if match:
        return {
            "tool": "device_detect_apps",
            "arguments": {
                "query": _clean_query(match.group(1)),
            },
            "kind": "app_detect",
        }

    return None


def app_control_intent(text: str) -> dict | None:
    command = normalize_command(text)
    lower = command.lower()

    # Preserve specialized device routing. These are not application names.
    if (
        "http://" in lower
        or "https://" in lower
        or "www." in lower
        or re.search(
            r"\b(?:open|launch|start)\s+(?:my\s+)?(?:project|file|folder|website|url)\b",
            lower,
        )
        or (" and search " in lower)
    ):
        return None

    # Compound tasks are planner tasks. The deterministic open/close
    # parser must not treat the entire remaining sentence as an application
    # name (for example: "Discord and send a message to Hamza").
    if re.search(
        r"\b(?:and|then|after\s+that)\b",
        lower,
        flags=re.IGNORECASE,
    ):
        return None

    patterns = (
        (r"^(?:open|launch|start)\s+(?:the\s+)?(.+?)(?:\s+app)?$", "open"),
        (r"^(?:close|quit|exit)\s+(?:the\s+)?(.+?)(?:\s+app)?$", "close"),
        (r"^(?:focus|switch\s+to|bring)\s+(?:the\s+)?(.+?)(?:\s+to\s+front)?$", "focus"),
        (r"^(?:minimize|hide)\s+(?:the\s+)?(.+)$", "minimize"),
        (r"^maximize\s+(?:the\s+)?(.+)$", "maximize"),
        (r"^restore\s+(?:the\s+)?(.+)$", "restore"),
    )

    for pattern, action in patterns:
        match = re.match(pattern, command, flags=re.IGNORECASE)

        if not match:
            continue

        app = _clean_query(match.group(1))

        if not app or app.lower() in GENERIC_APP_NOUNS:
            return None

        # Preserve historical open-app routing for old tests and simple opens.
        if action == "open":
            return {
                "tool": "device_open_app",
                "arguments": {
                    "app": app,
                },
                "kind": "app_open",
            }

        return {
            "tool": "device_app_control",
            "arguments": {
                "app": app,
                "action": action,
            },
            "kind": "app_control",
        }

    return None


def app_interaction_intent(text: str) -> dict | None:
    command = normalize_command(text)

    # Natural one-turn edit workflow, e.g.
    # "Open Notepad, type exactly: hello". Keep the typed payload separate
    # from the app name so app launch routing cannot swallow the whole command.
    match = re.match(
        r"^(?:open|launch|start)\s+(?:the\s+)?(.+?)\s*[,;]\s*"
        r"(?:and\s+)?(?:type|write)\s+(?:exactly\s*:?[\s]*)?(.+)$",
        command,
        flags=re.IGNORECASE,
    )

    if match:
        app = _clean_query(match.group(1))
        payload = str(match.group(2) or "").strip()
        if app and payload:
            return {
                "tool": "device_interact_app",
                "arguments": {
                    "app": app,
                    "actions": [
                        {
                            "action": "type",
                            "text": payload,
                        }
                    ],
                    "ensure_open": True,
                },
                "kind": "app_open_and_type",
            }

    match = re.match(
        r"^(?:open|launch|start)\s+(?:the\s+)?(.+?)"
        r"\s+and\s+search(?:\s+for)?\s+(.+)$",
        command,
        flags=re.IGNORECASE,
    )

    if match:
        app = _clean_query(match.group(1))
        query = _clean_query(match.group(2))

        if app.lower() in BROWSER_NAMES:
            return {
                "tool": "device_interact_app",
                "arguments": {
                    "app": app,
                    "actions": [
                        {
                            "action": "hotkey",
                            "keys": ["ctrl", "l"],
                        },
                        {
                            "action": "type",
                            "text": query,
                        },
                        {
                            "action": "press",
                            "key": "enter",
                        },
                    ],
                    "ensure_open": True,
                },
                "kind": "browser_search",
            }

    match = re.match(
        r"^(?:type|write)\s+(.+?)\s+(?:in|into)\s+(.+)$",
        command,
        flags=re.IGNORECASE,
    )

    if match:
        return {
            "tool": "device_interact_app",
            "arguments": {
                "app": _clean_query(match.group(2)),
                "actions": [
                    {
                        "action": "type",
                        "text": match.group(1),
                    }
                ],
                "ensure_open": True,
            },
            "kind": "app_interact",
        }

    match = re.match(
        r"^press\s+([a-z0-9]+)\s+(?:in|on)\s+(.+)$",
        command,
        flags=re.IGNORECASE,
    )

    if match:
        return {
            "tool": "device_interact_app",
            "arguments": {
                "app": _clean_query(match.group(2)),
                "actions": [
                    {
                        "action": "press",
                        "key": match.group(1).lower(),
                    }
                ],
                "ensure_open": True,
            },
            "kind": "app_interact",
        }

    match = re.match(
        r"^scroll\s+(up|down)\s+(?:in|on)\s+(.+)$",
        command,
        flags=re.IGNORECASE,
    )

    if match:
        amount = 3 if match.group(1).lower() == "up" else -3
        return {
            "tool": "device_interact_app",
            "arguments": {
                "app": _clean_query(match.group(2)),
                "actions": [
                    {
                        "action": "scroll",
                        "amount": amount,
                    }
                ],
                "ensure_open": True,
            },
            "kind": "app_interact",
        }

    match = re.match(
        r"^search\s+(.+?)\s+(?:in|on)\s+(.+)$",
        command,
        flags=re.IGNORECASE,
    )

    if match:
        query = _clean_query(match.group(1))
        app = _clean_query(match.group(2))

        if app.lower() in BROWSER_NAMES:
            return {
                "tool": "device_interact_app",
                "arguments": {
                    "app": app,
                    "actions": [
                        {
                            "action": "hotkey",
                            "keys": ["ctrl", "l"],
                        },
                        {
                            "action": "type",
                            "text": query,
                        },
                        {
                            "action": "press",
                            "key": "enter",
                        },
                    ],
                    "ensure_open": True,
                },
                "kind": "browser_search",
            }

    return None


def direct_device_intent(
    text: str,
    *,
    spotify_context: bool = False,
) -> dict | None:
    if _open_spotify_intent(text):
        return {
            "tool": "device_open_app",
            "arguments": {
                "app": "spotify",
            },
            "kind": "spotify_open",
        }

    detected = detect_apps_intent(text)
    if detected:
        return detected

    media = media_control_request_from_text(text)
    if media:
        return {
            "tool": "device_media_control",
            "arguments": media,
            "kind": "media_control",
        }

    search_query = spotify_search_query_from_text(
        text,
        spotify_context=spotify_context,
    )

    if search_query:
        return {
            "tool": "device_spotify_search",
            "arguments": {
                "query": search_query,
            },
            "kind": "spotify_search",
        }

    play_query = spotify_query_from_text(
        text,
        spotify_context=spotify_context,
    )

    if play_query:
        return {
            "tool": "device_spotify_play",
            "arguments": {
                "query": play_query,
            },
            "kind": "spotify_play",
        }

    interaction = app_interaction_intent(text)
    if interaction:
        return interaction

    lower = normalize_command(text).lower()
    if any(
        phrase in lower
        for phrase in (
            "open project",
            "open my project",
            "project in vs code",
            "project in vscode",
            "project in visual studio code",
        )
    ):
        return None

    app_action = app_control_intent(text)
    if app_action:
        return app_action

    return None


def _clean_device_error(value) -> str:
    error = str(value or "unknown device error").strip()
    prefix = re.compile(
        r"^(?:(?:RuntimeError|ValueError|PermissionError|"
        r"FileNotFoundError|TimeoutError|OSError):\s*)+"
    )
    cleaned = prefix.sub("", error).strip()
    return cleaned or "unknown device error"


def result_message(action: dict, result) -> str:
    tool = action.get("tool", "")
    arguments = action.get("arguments", {})

    if not result.ok:
        error = _clean_device_error(result.error)
        return "I couldn't complete that action on your PC: " + error

    if tool == "device_detect_apps":
        query = str(arguments.get("query", "")).strip()
        return (
            f"I checked installed/running apps matching “{query}”."
            if query
            else "I checked the installed and running apps on your PC."
        )

    if tool == "device_open_app":
        app = str(arguments.get("app", "the app"))
        return f"I opened {app} on your PC."

    if tool == "device_app_control":
        app = str(arguments.get("app", "the app"))
        command = str(arguments.get("action", "control"))
        return f"I sent the {command} command to {app}."

    if tool == "device_interact_app":
        app = str(arguments.get("app", "the app"))
        return f"I completed the requested interaction in {app}."

    if tool == "device_spotify_search":
        query = str(arguments.get("query", ""))
        return f"I opened Spotify search for “{query}”."

    if tool == "device_spotify_play":
        query = str(arguments.get("query", "that track"))
        return f"I searched Spotify and sent Play for “{query}”."

    if tool == "device_media_control":
        command = str(arguments.get("command", "media")).replace("_", " ")
        app = str(arguments.get("app", "")).strip()
        target = f" on {app}" if app else ""
        return f"I sent the {command} media command{target}."

    return "I completed the device action."
