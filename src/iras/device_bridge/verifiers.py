from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any


class SemanticVerifier:
    def __init__(self, executor: Any):
        self.executor = executor

    def verify(self, kind: str, target: str = "", **kwargs) -> dict:
        kind = str(kind or "").strip().lower()
        target = str(target or "").strip()
        if kind == "file_exists":
            path = self.executor._path(target, must_exist=False)
            return {"verified": path.exists(), "kind": kind, "target": str(path)}
        if kind == "file_absent":
            path = self.executor._path(target, must_exist=False)
            return {"verified": not path.exists(), "kind": kind, "target": str(path)}
        if kind == "directory_exists":
            path = self.executor._path(target, must_exist=False)
            return {"verified": path.is_dir(), "kind": kind, "target": str(path)}
        if kind == "foreground_title_contains":
            foreground = self.executor.computer._foreground()
            verified = target.casefold() in str(foreground.get("title") or "").casefold()
            return {"verified": verified, "kind": kind, "target": target, "foreground": foreground}
        if kind in {"screen_text", "text_contains"}:
            result = self.executor.computer.verify(
                condition="text_contains",
                target=target,
                vision=str(kwargs.get("vision") or "auto"),
                scope=str(kwargs.get("scope") or "foreground"),
            )
            return {"verified": bool(result.get("verified")), "kind": kind, "target": target, "evidence": result}
        if kind == "process_running":
            query = target.casefold()
            if os.name == "nt":
                cp = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace")
                text = cp.stdout.casefold()
            else:
                cp = subprocess.run(["ps", "-eo", "comm"], capture_output=True, text=True, errors="replace")
                text = cp.stdout.casefold()
            return {"verified": query in text, "kind": kind, "target": target}
        raise ValueError(
            "Unsupported verification kind. Use file_exists, file_absent, directory_exists, foreground_title_contains, screen_text, or process_running."
        )
