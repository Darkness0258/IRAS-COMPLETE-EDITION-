from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import json
from pathlib import Path
import threading
import time
import uuid
from typing import Any

from iras.security.redact import redact


@dataclass
class OperationTrace:
    name: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    started_at: float = field(default_factory=time.time)
    started_perf: float = field(default_factory=time.perf_counter)
    stages: list[dict[str, Any]] = field(default_factory=list)

    def stage(self, name: str, **payload: Any) -> None:
        self.stages.append({"name": name, "at_ms": int((time.perf_counter() - self.started_perf) * 1000), **payload})

    def finish(self, *, ok: bool, **payload: Any) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "ok": bool(ok),
            "started_at": self.started_at,
            "total_ms": int((time.perf_counter() - self.started_perf) * 1000),
            "stages": self.stages,
            **payload,
        }


class TraceLogger:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or (Path.home() / ".iras" / "traces.jsonl")).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(self, row: dict[str, Any]) -> None:
        safe = redact(dict(row))
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe, ensure_ascii=False, default=str) + "\n")

    @contextmanager
    def operation(self, name: str, **start_payload: Any):
        trace = OperationTrace(name=name)
        trace.stage("start", **start_payload)
        try:
            yield trace
        except Exception as exc:
            trace.stage("error", error=f"{type(exc).__name__}: {exc}")
            self.record(trace.finish(ok=False, error=f"{type(exc).__name__}: {exc}"))
            raise
        else:
            self.record(trace.finish(ok=True))
