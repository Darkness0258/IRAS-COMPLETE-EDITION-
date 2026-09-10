from __future__ import annotations
import re
from typing import Any

KEY_RE=re.compile(r'(api[_-]?key|token|password|secret|authorization|cookie|private[_-]?key)', re.I)
TOKEN_RE=re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}')

def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ('<redacted>' if KEY_RE.search(str(k)) else redact(v)) for k,v in value.items()}
    if isinstance(value, list): return [redact(v) for v in value]
    if isinstance(value, tuple): return tuple(redact(v) for v in value)
    if isinstance(value, str): return TOKEN_RE.sub(r'\1<redacted>', value)
    return value
