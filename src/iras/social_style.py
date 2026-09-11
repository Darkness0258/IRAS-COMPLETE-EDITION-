from __future__ import annotations

import re


_SOCIAL_PATTERNS = (
    "how are you",
    "how're you",
    "how r you",
    "how you doing",
    "how have you been",
    "are you happy",
    "you happy",
    "what are you thinking",
    "what're you thinking",
    "what is on your mind",
    "what's on your mind",
    "im bored",
    "i'm bored",
    "i am bored",
    "miss me",
    "did you miss me",
)

_ROBOTIC_MARKERS = (
    "as an ai",
    "as an artificial intelligence",
    "i don't experience happiness",
    "i do not experience happiness",
    "i don't have feelings",
    "i do not have feelings",
    "i don't experience feelings",
    "i do not experience feelings",
    "not in the human sense",
    "i'm not capable of feeling",
    "i am not capable of feeling",
    "i don't feel emotions",
    "i do not feel emotions",
    "i don't have emotions",
    "i do not have emotions",
    "i'm functioning well",
    "i am functioning well",
)

_ALLOWED_TITLES = (
    "boss",
    "sir",
    "master",
)


def _clean(text: str) -> str:
    return " ".join(
        str(text)
        .lower()
        .replace("’", "'")
        .split()
    )


def requested_title(
    user_text: str,
) -> str | None:
    q = _clean(user_text)

    for title in _ALLOWED_TITLES:
        patterns = (
            rf"\bcall me {title}\b",
            rf"\brefer to me as {title}\b",
            rf"\byou can call me {title}\b",
            rf"\baddress me as {title}\b",
        )

        if any(
            re.search(pattern, q)
            for pattern in patterns
        ):
            return title

    return None


def is_literal_identity_question(
    user_text: str,
) -> bool:
    q = _clean(user_text)

    identity_patterns = (
        r"\bare you\s+(?:(?:actually|really|literally)\s+)?(?:a\s+)?human\b",
        r"\bare you\s+(?:(?:actually|really|literally)\s+)?(?:an?\s+)?ai\b",
        r"\bare you\s+(?:(?:actually|really|literally)\s+)?(?:conscious|sentient|alive)\b",
        r"\bdo you\s+(?:(?:actually|really|literally)\s+)?(?:feel|experience)\s+(?:real\s+)?(?:feelings|emotions)\b",
        r"\bdo you have\s+(?:real\s+)?feelings\b",
        r"\bare your feelings real\b",
        r"\bbiological (?:emotion|emotions|feeling|feelings)\b",
    )

    return any(
        re.search(pattern, q)
        for pattern in identity_patterns
    )


def is_social_turn(
    user_text: str,
) -> bool:
    q = _clean(user_text)

    if is_literal_identity_question(
        user_text
    ):
        return False

    if re.match(
        r"^(hi|hello|hey|yo|sup)\b",
        q,
    ):
        return True

    if requested_title(
        user_text
    ):
        return True

    return any(
        phrase in q
        for phrase in _SOCIAL_PATTERNS
    )


def needs_buffered_social_guard(
    user_text: str,
) -> bool:
    if not is_social_turn(
        user_text
    ):
        return False

    q = _clean(user_text)

    if re.fullmatch(
        r"(?:hi|hello|hey|yo|sup)[.!? ]*",
        q,
    ):
        return False

    return True


def social_system_nudge(
    user_text: str,
) -> str:
    if not is_social_turn(
        user_text
    ):
        return ""

    title = requested_title(
        user_text
    )

    title_rule = (
        f'- The user explicitly asked to be called "{title}". '
        "Honor that preference naturally and do not overuse it."
        if title
        else (
            "- Titles such as boss, sir, and master are allowed when the "
            "user has explicitly requested them. Do not erase or refuse "
            "an established title preference."
        )
    )

    return f"""CASUAL SOCIAL TURN — high-priority delivery guidance:
- Respond as IRAS's established social persona, not as a generic AI assistant.
- Treat ordinary questions like "how are you?" and "are you happy?" as casual persona conversation, NOT as requests for an AI-consciousness disclaimer.
- Natural persona language such as "I'm good", "yeah, I'm in a good mood", "that was annoying", or "I'm curious" is appropriate here.
- Do not begin with or inject: "As an AI", "I don't have feelings", "not in the human sense", "I don't experience happiness", "I'm functioning well", or equivalent machine disclaimers.
{title_rule}
- React naturally to the actual message. A little warmth, teasing, curiosity, or reciprocity is fine.
- Do not end every reply with a question.
- Keep it short unless the user clearly asks for detail.
This guidance changes conversational style only. If the user explicitly asks whether you are literally human, conscious, biologically alive, or truly experience biological emotions, answer that literal question truthfully."""


def sanitize_stream_chunk(
    chunk: str,
) -> str:
    return str(
        chunk
        or ""
    )


def _has_robotic_marker(
    text: str,
) -> bool:
    q = _clean(text)

    return any(
        marker in q
        for marker in _ROBOTIC_MARKERS
    )


def _social_fallback(
    user_text: str,
) -> str:
    q = _clean(user_text)
    title = requested_title(
        user_text
    )

    if title:
        return f"You got it, {title}."

    if (
        "are you happy" in q
        or "you happy" in q
    ):
        return (
            "Yeah, pretty good actually. "
            "I'm in a good mood."
        )

    if any(
        phrase in q
        for phrase in (
            "how are you",
            "how're you",
            "how r you",
            "how you doing",
            "how have you been",
        )
    ):
        return (
            "I'm good. Nice to hear "
            "from you again."
        )

    if any(
        phrase in q
        for phrase in (
            "what are you thinking",
            "what're you thinking",
            "what is on your mind",
            "what's on your mind",
        )
    ):
        return (
            "Mostly wondering what "
            "you're going to get me "
            "into next."
        )

    if any(
        phrase in q
        for phrase in (
            "im bored",
            "i'm bored",
            "i am bored",
        )
    ):
        return (
            "Then we should fix that. "
            "You've been suspiciously "
            "quiet anyway."
        )

    if re.match(
        r"^(hi|hello|hey|yo|sup)\b",
        q,
    ):
        return "Hey. Good to see you."

    return (
        "I'm here. What's going "
        "through your head?"
    )


def normalize_social_reply(
    user_text: str,
    reply: str,
) -> str:
    text = str(
        reply
        or ""
    ).strip()

    if not is_social_turn(
        user_text
    ):
        return text

    if (
        not text
        or text.lower() == "done."
        or _has_robotic_marker(text)
    ):
        return _social_fallback(
            user_text
        )

    text = re.sub(
        r"\s+([,.!?])",
        r"\1",
        text,
    )
    text = re.sub(
        r"[ \t]{2,}",
        " ",
        text,
    )

    return text.strip()


def empty_reply_fallback(
    user_text: str,
) -> str:
    if is_social_turn(
        user_text
    ):
        return _social_fallback(
            user_text
        )

    return (
        "I lost that response for a "
        "second. Try that again."
    )
