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
    r"^search\s+spotify\s+for\s+(.+)$",
    r"^search\s+for\s+(.+?)\s+on\s+spotify$",
    r"^search\s+(.+?)\s+on\s+spotify$",
    r"^find\s+(.+?)\s+on\s+spotify$",
    r"^look\s+up\s+(.+?)\s+on\s+spotify$",
    r"^spotify\s+search\s+(?:for\s+)?(.+)$",
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


def _normalize_voice_music_form(command: str) -> str:
    match = re.match(
        r"^(?:yeah|yah|ya)\s+(.+\b(?:song|track|music|playlist|album)\b.*)$",
        command,
        flags=re.IGNORECASE,
    )

    if match:
        return (
            "play "
            + match.group(1)
        )

    return command


def is_retry_phrase(text: str) -> bool:
    return (
        normalize_command(text).lower()
        in RETRY_PHRASES
    )


def media_control_from_text(
    text: str,
) -> str | None:
    command = normalize_command(
        text
    ).lower()

    for pattern, action in MEDIA_CONTROL_PATTERNS:
        if re.match(
            pattern,
            command,
            flags=re.IGNORECASE,
        ):
            return action

    return None


def spotify_search_query_from_text(
    text: str,
) -> str | None:
    command = _normalize_voice_music_form(
        normalize_command(
            text
        )
    )

    for pattern in SEARCH_PATTERNS:
        match = re.match(
            pattern,
            command,
            flags=re.IGNORECASE,
        )

        if match:
            query = _clean_query(
                match.group(1)
            )

            return (
                query
                if query
                else None
            )

    return None


def spotify_query_from_text(
    text: str,
    *,
    spotify_context: bool = False,
) -> str | None:
    command = _normalize_voice_music_form(
        normalize_command(
            text
        )
    )

    lower = command.lower()

    if any(
        destination in lower
        for destination in NON_SPOTIFY_DESTINATIONS
    ):
        return None

    explicit_spotify = (
        "spotify" in lower
    )

    query = None

    for pattern in PLAY_PATTERNS:
        match = re.match(
            pattern,
            command,
            flags=re.IGNORECASE,
        )

        if match:
            query = _clean_query(
                match.group(1)
            )
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
            or query_lower.startswith(
                name + " "
            )
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


def _open_spotify_intent(
    text: str,
) -> bool:
    command = normalize_command(
        text
    ).lower()

    return bool(
        re.match(
            r"^(?:open|launch|start)\s+(?:the\s+)?spotify(?:\s+app)?$",
            command,
        )
    )


def direct_device_intent(
    text: str,
    *,
    spotify_context: bool = False,
) -> dict | None:
    if _open_spotify_intent(
        text
    ):
        return {
            "tool": "device_open_app",
            "arguments": {
                "app": "spotify",
            },
            "kind": "spotify_open",
        }

    control = media_control_from_text(
        text
    )

    if control:
        return {
            "tool": "device_media_control",
            "arguments": {
                "command": control,
            },
            "kind": "media_control",
        }

    search_query = (
        spotify_search_query_from_text(
            text
        )
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

    return None


def result_message(
    action: dict,
    result,
) -> str:
    tool = action.get(
        "tool",
        "",
    )

    arguments = action.get(
        "arguments",
        {},
    )

    if not result.ok:
        error = str(
            result.error
            or "unknown device error"
        )

        return (
            "I couldn't complete that action on your PC: "
            + error
        )

    if tool == "device_open_app":
        return "I opened Spotify on your PC."

    if tool == "device_spotify_search":
        query = str(
            arguments.get(
                "query",
                "",
            )
        )

        return (
            "I opened Spotify search for "
            f"“{query}”."
        )

    if tool == "device_spotify_play":
        query = str(
            arguments.get(
                "query",
                "that track",
            )
        )

        return (
            "I sent Spotify the command to search for and play "
            f"“{query}”."
        )

    if tool == "device_media_control":
        command = str(
            arguments.get(
                "command",
                "media",
            )
        ).replace(
            "_",
            " ",
        )

        return (
            f"I sent the {command} command to Spotify."
        )

    return "I completed the device action."
