from __future__ import annotations

import re


RETRY_PHRASES = {
    "again",
    "do it again",
    "retry",
    "retry it",
    "try again",
    "try it again",
}

MEDIA_CONTROL_PHRASES = {
    "play the song": "play",
    "play song": "play",
    "play the music": "play",
    "play music": "play",
    "resume the song": "resume",
    "resume song": "resume",
    "resume the music": "resume",
    "resume music": "resume",
    "pause the song": "pause",
    "pause song": "pause",
    "pause the music": "pause",
    "pause music": "pause",
    "next song": "next",
    "next track": "next",
    "skip song": "next",
    "skip track": "next",
    "previous song": "previous",
    "previous track": "previous",
    "last song": "previous",
    "stop the song": "stop",
    "stop song": "stop",
    "stop the music": "stop",
    "stop music": "stop",
    "mute the music": "mute",
    "mute music": "mute",
    "volume up": "volume_up",
    "increase volume": "volume_up",
    "volume down": "volume_down",
    "decrease volume": "volume_down",
}


def normalize_command(text: str) -> str:
    value = " ".join(str(text or "").strip().split())
    value = re.sub(
        r"^(?:hey\s+)?(?:iras|iris|eris|eras)\s*[,.:;!?-]*\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return value.strip()


def is_retry_phrase(text: str) -> bool:
    return normalize_command(text).lower() in RETRY_PHRASES


def _generic_media_phrase(text: str) -> dict | None:
    normalized = normalize_command(text).lower()
    command = MEDIA_CONTROL_PHRASES.get(normalized)
    if not command:
        return None
    return {
        "tool": "device_media_control",
        "arguments": {"command": command},
        "kind": "media_control",
    }


def spotify_query_from_text(
    text: str,
    *,
    spotify_context: bool = False,
) -> str | None:
    command = normalize_command(text)
    lower = command.lower()
    explicit_spotify = "spotify" in lower

    patterns = (
        r"^(?:open\s+spotify\s+(?:and\s+)?)?play\s+(.+?)(?:\s+on\s+spotify)?$",
        r"^spotify\s+play\s+(.+)$",
    )

    query = None
    for pattern in patterns:
        match = re.match(pattern, command, flags=re.IGNORECASE)
        if match:
            query = match.group(1).strip(" \t,.:;!?-")
            break

    if not query:
        return None

    query_lower = query.lower()
    if query_lower in {
        "song",
        "the song",
        "music",
        "the music",
        "it",
        "that",
        "that song",
        "this song",
    }:
        return None

    looks_like_music = bool(
        re.search(
            r"\b(song|track|music|album|playlist)\b",
            query_lower,
        )
    )

    if not (explicit_spotify or spotify_context or looks_like_music):
        return None

    return query


def direct_device_intent(
    text: str,
    *,
    spotify_context: bool = False,
) -> dict | None:
    media = _generic_media_phrase(text)
    if media:
        return media

    query = spotify_query_from_text(
        text,
        spotify_context=spotify_context,
    )
    if query:
        return {
            "tool": "device_spotify_play",
            "arguments": {"query": query},
            "kind": "spotify_play",
        }

    return None


def result_message(action: dict, result) -> str:
    tool = action.get("tool", "")
    arguments = action.get("arguments", {})

    if not result.ok:
        error = str(result.error or "unknown device error")
        return "I couldn't complete that action on your PC: " + error

    if tool == "device_spotify_play":
        query = str(arguments.get("query", "that song"))
        return (
            "I sent Spotify the command to search for and play "
            f"“{query}”."
        )

    if tool == "device_media_control":
        command = str(arguments.get("command", "media")).replace("_", " ")
        return f"I sent the {command} media command to your PC."

    return "I completed the device action."
