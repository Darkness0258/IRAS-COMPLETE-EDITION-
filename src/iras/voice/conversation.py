
from __future__ import annotations

import re


DEFAULT_IRAS_WAKE_ALIASES = (
    "iras",
    "iris",
    "eris",
    "eras",
    "eye ris",
    "eye-ris",
    "eye ras",
    "eye-rass",
    "ira's",
    "i r a s",
    "little girl",
    "cute",
)


def normalize_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", str(text).lower())


def wake_aliases(wake_word: str = "iras") -> tuple[str, ...]:
    primary = str(wake_word or "iras").strip().lower()

    if primary == "iras":
        return DEFAULT_IRAS_WAKE_ALIASES

    return (primary,)


def _alias_regex(alias: str) -> str:
    pieces = re.findall(r"[a-z0-9']+", alias.lower())

    if not pieces:
        return re.escape(alias)

    return r"[\s-]*".join(
        re.escape(piece)
        for piece in pieces
    )


def _wake_regex(wake_word: str = "iras") -> str:
    aliases = sorted(
        wake_aliases(wake_word),
        key=len,
        reverse=True,
    )

    return "(?:" + "|".join(
        _alias_regex(alias)
        for alias in aliases
    ) + ")"


def extract_wake_command(
    text: str,
    wake_word: str = "iras",
    *,
    armed: bool = False,
) -> tuple[bool, str]:
    raw = str(text or "").strip()

    if not raw:
        return False, ""

    wake = _wake_regex(wake_word)

    # Match aliases only at the beginning of the utterance to reduce
    # accidental wake-ups from common words such as "cute".
    pattern = re.compile(
        rf"(?i)^\s*(?:(?:hey|okay|ok)\s+)?{wake}\b"
        r"[\s,.:;!?-]*(.*)$"
    )

    match = pattern.match(raw)

    if match:
        return True, match.group(1).strip()

    if armed:
        return True, raw

    return False, ""


def is_wake_only_phrase(
    text: str,
    wake_word: str = "iras",
) -> bool:
    accepted, command = extract_wake_command(
        text,
        wake_word,
        armed=False,
    )
    return accepted and not command


def is_probable_echo(
    transcript: str,
    spoken_text: str,
    *,
    wake_word: str = "iras",
    threshold: float = 0.68,
) -> bool:
    heard = normalize_words(transcript)
    spoken = normalize_words(spoken_text)

    if not heard or not spoken:
        return False

    if is_wake_only_phrase(
        transcript,
        wake_word,
    ):
        return False

    heard_set = set(heard)
    spoken_set = set(spoken)

    overlap = len(
        heard_set & spoken_set
    ) / max(
        1,
        len(heard_set),
    )

    if len(heard_set) == 1:
        return overlap >= 1.0

    return overlap >= float(threshold)


def pop_complete_sentences(
    buffer: str,
    *,
    force: bool = False,
) -> tuple[list[str], str]:
    remaining = str(buffer or "")
    sentences: list[str] = []
    pattern = re.compile(r"^([\s\S]*?[.!?])(?=\s|$)")

    while True:
        match = pattern.match(remaining)

        if not match:
            break

        sentence = match.group(1).strip()
        remaining = remaining[match.end():].lstrip()

        if sentence:
            sentences.append(sentence)

    if force and remaining.strip():
        sentences.append(remaining.strip())
        remaining = ""

    return sentences, remaining
