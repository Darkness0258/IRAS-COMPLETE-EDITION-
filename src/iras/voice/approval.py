from __future__ import annotations

from dataclasses import dataclass
import os
import re
import secrets
from typing import Any

from iras.models import ApprovalRequest, PermissionLevel


_DIGIT_WORDS = {
    "zero": "0",
    "oh": "0",
    "one": "1",
    "two": "2",
    "to": "2",
    "too": "2",
    "three": "3",
    "four": "4",
    "for": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "ate": "8",
    "nine": "9",
}


def _truthy(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", str(text or "").lower())


def _digits(text: str) -> str:
    values: list[str] = []
    for token in _words(text):
        if token.isdigit():
            values.extend(list(token))
        elif token in _DIGIT_WORDS:
            values.append(_DIGIT_WORDS[token])
    return "".join(values)


def _has_iras(text: str) -> bool:
    normalized = " ".join(_words(text))
    return bool(
        re.search(
            r"\b(?:iras|iris|eris|eras|i\s+r\s+a\s+s|eye\s+ris|eye\s+ras)\b",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _deny(text: str) -> bool:
    normalized = " ".join(_words(text))
    return bool(
        re.search(
            r"\b(?:deny|denied|cancel|stop|reject|no|nope|nah|mat|nahi|nahin)\b",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _approve(text: str) -> bool:
    normalized = " ".join(_words(text))
    return bool(
        re.search(
            r"\b(?:approve|approved|allow|authorize|authorise|go ahead|do it|yes approve|haan approve|han approve)\b",
            normalized,
            flags=re.IGNORECASE,
        )
    )


@dataclass(slots=True)
class VoiceApprovalResult:
    resolved: bool
    approved: bool = False
    heard: str = ""
    method: str = "voice"
    reason: str = ""
    challenge: str = ""


class VoiceApprovalManager:
    """Local microphone authorization for interactive IRAS approvals.

    Voice approval is an interaction convenience, not biometric speaker
    authentication. Normal SYSTEM_ACTION requests require an explicit IRAS +
    approve phrase. CRITICAL requests additionally require a fresh four-digit
    spoken challenge, preventing a generic background "yes" from authorizing a
    destructive command.
    """

    def __init__(
        self,
        listener: Any,
        speaker: Any | None = None,
        *,
        enabled: bool | None = None,
        critical_enabled: bool | None = None,
        timeout_seconds: int | None = None,
    ):
        self.listener = listener
        self.speaker = speaker
        self.enabled = _truthy("IRAS_VOICE_APPROVALS", True) if enabled is None else bool(enabled)
        self.critical_enabled = (
            _truthy("IRAS_VOICE_APPROVAL_CRITICAL", True)
            if critical_enabled is None
            else bool(critical_enabled)
        )
        self.timeout_seconds = (
            _int_env("IRAS_VOICE_APPROVAL_TIMEOUT", 9, 3, 30)
            if timeout_seconds is None
            else max(3, min(int(timeout_seconds), 30))
        )

    @staticmethod
    def _summary(request: ApprovalRequest) -> str:
        # Never read command arguments aloud: terminal invocations can contain
        # tokens, file names, URLs, or other private data. The visible approval
        # surface can show redacted details without leaking them through audio.
        return str(request.tool_name or "action").replace("_", " ")

    def _speak(self, text: str) -> None:
        if self.speaker is None:
            return
        try:
            self.speaker.speak(text)
        except Exception:
            # Speech output is optional; microphone recognition can still work
            # with the on-screen/console prompt supplied by the caller.
            pass

    def _listen(self) -> str:
        if self.listener is None:
            return ""
        try:
            listen_phrase = getattr(self.listener, "listen_phrase", None)
            if callable(listen_phrase):
                return str(
                    listen_phrase(
                        start_timeout=float(self.timeout_seconds),
                        max_seconds=float(self.timeout_seconds),
                        silence_seconds=0.75,
                    )
                    or ""
                ).strip()
            listen_once = getattr(self.listener, "listen_once", None)
            if callable(listen_once):
                return str(listen_once() or "").strip()
        except Exception:
            return ""
        return ""

    @staticmethod
    def _challenge_code() -> str:
        # Exclude repeated digits only by chance; four random decimal digits are
        # short enough for Whisper/Android-style recognition while still making
        # stale/background approvals extremely unlikely.
        return "".join(str(secrets.randbelow(10)) for _ in range(4))

    @staticmethod
    def _spoken_code(code: str) -> str:
        names = {
            "0": "zero",
            "1": "one",
            "2": "two",
            "3": "three",
            "4": "four",
            "5": "five",
            "6": "six",
            "7": "seven",
            "8": "eight",
            "9": "nine",
        }
        return " ".join(names[d] for d in code)

    def request(self, request: ApprovalRequest) -> VoiceApprovalResult:
        if not self.enabled:
            return VoiceApprovalResult(False, reason="voice approvals disabled")

        if request.permission >= PermissionLevel.CRITICAL:
            if not self.critical_enabled:
                return VoiceApprovalResult(False, reason="critical voice approvals disabled")

            challenge = self._challenge_code()
            phrase = self._spoken_code(challenge)
            self._speak(
                "Critical permission requested. "
                f"Say: IRAS authorize {phrase}. Say IRAS deny to cancel."
            )
            heard = self._listen()
            if not heard:
                return VoiceApprovalResult(False, heard="", reason="no speech", challenge=challenge)
            if _deny(heard):
                return VoiceApprovalResult(True, False, heard=heard, reason="spoken denial", challenge=challenge)
            authorized = _has_iras(heard) and bool(re.search(r"\b(?:authorize|authorise|approve)\b", " ".join(_words(heard))))
            if authorized and _digits(heard).endswith(challenge):
                return VoiceApprovalResult(True, True, heard=heard, reason="critical challenge matched", challenge=challenge)
            return VoiceApprovalResult(False, False, heard=heard, reason="critical challenge did not match", challenge=challenge)

        self._speak(
            f"Permission requested for {self._summary(request)}. "
            "Say IRAS approve to allow it, or IRAS deny to cancel."
        )
        heard = self._listen()
        if not heard:
            return VoiceApprovalResult(False, heard="", reason="no speech")
        if _deny(heard):
            return VoiceApprovalResult(True, False, heard=heard, reason="spoken denial")
        if _has_iras(heard) and _approve(heard):
            return VoiceApprovalResult(True, True, heard=heard, reason="spoken approval")
        return VoiceApprovalResult(False, False, heard=heard, reason="unrecognized approval phrase")
