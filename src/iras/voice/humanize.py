from __future__ import annotations

import html
import re
import unicodedata


# Common emoji ranges. Variation selectors and ZWJ are also removed so
# compound emoji do not leak odd words into TTS.
_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"  # flags
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\u2600-\u27BF"
    "\uFE0F"
    "\u200D"
    "]+",
    flags=re.UNICODE,
)

_FENCED_CODE_RE = re.compile(r"```[\w.+-]*\s*\n?.*?```", re.DOTALL)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:https?://|mailto:)[^)]+\)")
_RAW_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TABLE_RULE_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_QUOTE_RE = re.compile(r"^\s*>\s?")
_MULTI_PUNCT_RE = re.compile(r"([!?.,])\1{2,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def _remove_emoji_and_decorative_symbols(text: str) -> str:
    text = _EMOJI_RE.sub("", text)

    out: list[str] = []
    for ch in text:
        cat = unicodedata.category(ch)

        # Keep ordinary punctuation and useful math/currency in technical
        # sentences, but remove decorative/emoji-like symbol characters.
        if cat == "So":
            continue

        # Common chat decorations that speech engines often pronounce.
        if ch in {"★", "☆", "◆", "◇", "■", "□", "●", "○", "♥", "♡"}:
            continue

        out.append(ch)

    return "".join(out)


def speech_text(text: str) -> str:
    """
    Convert display-oriented assistant text into natural TTS text.

    The original response is never changed on screen. This function only
    produces the string sent to the speech synthesizer.
    """
    if not text:
        return ""

    value = html.unescape(str(text)).replace("\r\n", "\n").replace("\r", "\n")

    had_code = bool(_FENCED_CODE_RE.search(value))
    value = _FENCED_CODE_RE.sub("\n", value)

    # Markdown links keep the human-readable label, not the URL.
    value = _MARKDOWN_LINK_RE.sub(r"\1", value)

    # A person normally does not read a full URL aloud in conversation.
    value = _RAW_URL_RE.sub("", value)

    # Inline code keeps its words but loses backticks.
    value = re.sub(r"`([^`\n]+)`", r"\1", value)

    # Strip simple HTML before symbol cleanup.
    value = _HTML_TAG_RE.sub("", value)

    cleaned_lines: list[str] = []
    for raw in value.splitlines():
        if _TABLE_RULE_RE.match(raw):
            continue

        line = _HEADING_RE.sub("", raw)
        line = _QUOTE_RE.sub("", line)
        line = _LIST_RE.sub("", line)

        # Markdown emphasis / strike markers should never be spoken.
        line = line.replace("**", "").replace("__", "").replace("~~", "")
        line = line.replace("*", "").replace("_", "")

        # Table pipes and arrows become normal conversational pauses/words.
        line = line.replace("->", " to ").replace("→", " to ")
        line = line.replace("<-", " from ").replace("←", " from ")
        line = line.replace("|", ". ")

        # Do not have TTS announce markdown/code punctuation.
        line = line.replace("`", "").replace("#", "")

        line = _remove_emoji_and_decorative_symbols(line)
        line = _MULTI_SPACE_RE.sub(" ", line).strip()

        if line:
            cleaned_lines.append(line)

    value = "\n".join(cleaned_lines)
    value = _MULTI_PUNCT_RE.sub(r"\1", value)
    value = _MULTI_BLANK_RE.sub("\n\n", value)
    value = value.strip()

    # If a response is mainly a code block, a human assistant would point
    # to the screen instead of reading syntax character-by-character.
    if not value and had_code:
        return "I put the code on screen."

    return value
