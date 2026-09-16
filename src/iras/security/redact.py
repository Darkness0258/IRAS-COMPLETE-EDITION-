from __future__ import annotations
import re
from typing import Any

KEY_RE = re.compile(r'(api[_-]?key|token|password|secret|authorization|cookie|private[_-]?key|credential)', re.I)
TOKEN_RE = re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}')
ENV_SECRET_RE = re.compile(
    r'(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|PRIVATE[_-]?KEY|CREDENTIAL)[A-Z0-9_]*)\s*([:=])\s*([^\s,;]+)'
)
KNOWN_TOKEN_RE = re.compile(
    r'(?i)\b(?:sk-(?:or-v1-)?[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b'
)
JWT_RE = re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b')


def _redact_string(value: str) -> str:
    text = TOKEN_RE.sub(r'\1<redacted>', value)
    text = ENV_SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>", text)
    text = KNOWN_TOKEN_RE.sub('<redacted-token>', text)
    text = JWT_RE.sub('<redacted-jwt>', text)
    return text


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ('<redacted>' if KEY_RE.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact(v) for v in value)
    if isinstance(value, str):
        return _redact_string(value)
    return value
