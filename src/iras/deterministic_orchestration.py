from __future__ import annotations

from dataclasses import dataclass
from pathlib import PureWindowsPath
import re
from typing import Any, Callable


@dataclass(frozen=True)
class ExactFileObjective:
    path: str
    content: str

    @property
    def repo(self) -> str:
        return str(PureWindowsPath(self.path).parent)


_EXACT_FILE_RE = re.compile(
    r"\bcreate\s+(?P<path>[A-Za-z]:\\.+?\.txt)\s+containing\s+exactly\s+"
    r"(?P<quote>[\"'“])(?P<content>.*?)(?P=quote)",
    flags=re.IGNORECASE | re.DOTALL,
)


def parse_exact_file_objective(text: str) -> ExactFileObjective | None:
    """Parse only the narrow, reversible exact-text-file objective IRAS can execute deterministically."""
    raw = str(text or "").strip()
    match = _EXACT_FILE_RE.search(raw)
    if not match:
        # Curly closing quote is not the same codepoint as the opening one.
        match = re.search(
            r"\bcreate\s+(?P<path>[A-Za-z]:\\.+?\.txt)\s+containing\s+exactly\s+[“\"](?P<content>.*?)[”\"]",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
    if not match:
        return None

    path = " ".join(str(match.group("path") or "").strip().split())
    content = str(match.group("content") or "")
    if not path or len(path) > 1000 or len(content) > 20000:
        return None
    if any(token in path for token in ("*", "?", "\x00", "%", "${", "..\\")):
        return None
    try:
        parsed = PureWindowsPath(path)
    except Exception:
        return None
    if not parsed.drive or parsed.suffix.lower() != ".txt":
        return None
    return ExactFileObjective(path=str(parsed), content=content)


def exact_file_plan(objective: str) -> list[dict[str, Any]] | None:
    parsed = parse_exact_file_objective(objective)
    if not parsed:
        return None
    return [
        {
            "id": "create-file",
            "title": "Create exact text file",
            "prompt": f"Create {parsed.path} containing exactly the requested text and modify no other file.",
            "role": "coder",
            "priority": 90,
            "depends_on": [],
            "max_retries": 1,
        },
        {
            "id": "verify-file",
            "title": "Verify exact file content",
            "prompt": f"Verify {parsed.path} exists and contains exactly the requested text.",
            "role": "tester",
            "priority": 80,
            "depends_on": ["create-file"],
            "max_retries": 1,
        },
        {
            "id": "review-operation",
            "title": "Review operation safety",
            "prompt": "Review the operation for safety and confirm whether unrelated project files changed.",
            "role": "reviewer",
            "priority": 70,
            "depends_on": ["verify-file"],
            "max_retries": 1,
        },
    ]


def deterministic_exact_file_task(
    *,
    role: str,
    objective: str,
    dependency_results: list[dict[str, Any]],
    request: Callable[[str, dict[str, Any], int], Any],
) -> dict[str, Any] | None:
    """Execute/verify one narrow file objective without an LLM.

    This never executes shell or arbitrary commands. The callback still routes through the
    normal IRAS remote queue, declared permission, local policy, allowed-root checks, and
    emergency-stop controller.
    """
    parsed = parse_exact_file_objective(objective)
    if not parsed:
        return None
    role = str(role or "general").strip().lower()

    if role == "coder":
        result = request(
            "write_text",
            {"path": parsed.path, "content": parsed.content, "append": False},
            60,
        )
        return {
            "result": (
                f"Deterministic file write completed: {parsed.path}. "
                f"Windows reported {int((result or {}).get('bytes') or 0)} byte(s) written."
            ),
            "metrics": {"deterministic_fallback": True, "action": "write_text"},
        }

    if role == "tester":
        result = request(
            "read_text",
            {"path": parsed.path, "max_chars": max(1, min(len(parsed.content) + 64, 20000))},
            45,
        )
        actual = str((result or {}).get("content") or "")
        if actual != parsed.content:
            raise RuntimeError(
                "Deterministic verification failed: file content does not exactly match the requested text."
            )
        return {
            "result": f"Verified {parsed.path}: the file exists and its content matches exactly.",
            "metrics": {"deterministic_fallback": True, "action": "read_text", "exact_match": True},
        }

    if role == "reviewer":
        status = request("git_status", {"repo": parsed.repo}, 45)
        stdout = str((status or {}).get("stdout") or "")
        lines = [line.rstrip() for line in stdout.splitlines() if line.strip()]
        changed = [line for line in lines if not line.startswith("##")]
        basename = PureWindowsPath(parsed.path).name.lower()
        unrelated = [line for line in changed if basename not in line.lower()]
        if unrelated:
            verdict = "Review found other working-tree changes already present or created; they require separate inspection: " + "; ".join(unrelated[:12])
        else:
            verdict = "Review found no unrelated Git working-tree changes; only the requested file is visible as changed/untracked."
        return {
            "result": verdict,
            "metrics": {
                "deterministic_fallback": True,
                "action": "git_status",
                "unrelated_change_count": len(unrelated),
            },
        }

    if role == "coordinator":
        parts = []
        failed = []
        for item in dependency_results or []:
            state = str(item.get("state") or "")
            title = str(item.get("title") or item.get("task_id") or "task")
            if state == "succeeded":
                parts.append(f"{title}: {str(item.get('result') or '').strip()}")
            elif state:
                failed.append(f"{title}={state}: {str(item.get('error') or '').strip()}")
        if failed:
            summary = "Objective was not fully verified. " + " | ".join(failed)
        else:
            summary = "Objective completed and verified. " + " | ".join(parts)
        return {
            "result": summary[:12000],
            "metrics": {"deterministic_fallback": True, "action": "final_synthesis"},
        }

    return None
