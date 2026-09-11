from __future__ import annotations
import re

def normalize_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", str(text).lower())

def extract_wake_command(
    text: str,
    wake_word: str = "iras",
    *,
    armed: bool = False,
) -> tuple[bool, str]:
    raw = str(text or "").strip()
    if not raw:
        return False, ""
    wake = re.escape(str(wake_word or "iras").strip() or "iras")
    pattern = re.compile(
        rf"(?i)\b(?:(?:hey|okay|ok)\s+)?{wake}\b[\s,.:;!?-]*(.*)$"
    )
    match = pattern.search(raw)
    if match:
        return True, match.group(1).strip()
    if armed:
        return True, raw
    return False, ""

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
    wake = normalize_words(wake_word)
    if len(heard) == 1 and wake and heard[0] == wake[-1]:
        return False
    hs, ss = set(heard), set(spoken)
    overlap = len(hs & ss) / max(1, len(hs))
    if len(hs) == 1:
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
