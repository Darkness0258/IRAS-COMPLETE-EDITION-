from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from .common import new_id, utc_now


_BRANCH = re.compile(r"[^A-Za-z0-9._/-]+")


@dataclass
class CodingWorkspace:
    workspace_id: str
    repo: str
    path: str
    branch: str
    base_ref: str
    created_at: str


class CodingWorkspaceManager:
    """Isolated Git worktrees for coding agents.

    No merge is automatic. `merge_plan` only reports the command/ref a human or
    higher-level approved workflow could execute.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _git(repo: Path, *args: str, timeout: int = 60) -> str:
        proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout, shell=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"git exited {proc.returncode}")
        return proc.stdout.strip()

    def create(self, repo: str | Path, *, name: str, base_ref: str = "HEAD") -> CodingWorkspace:
        repo = Path(repo).resolve()
        if not (repo / ".git").exists() and not self._git(repo, "rev-parse", "--git-dir"):
            raise ValueError("Repository is not a Git worktree.")
        wid = new_id("ws_")[:15]
        safe = _BRANCH.sub("-", name.strip().lower()).strip("-./") or "task"
        branch = f"iras/{safe}-{wid[-6:]}"
        path = self.root / wid
        self._git(repo, "worktree", "add", "-b", branch, str(path), base_ref, timeout=120)
        return CodingWorkspace(wid, str(repo), str(path), branch, base_ref, utc_now())

    def status(self, workspace: CodingWorkspace) -> str:
        return self._git(Path(workspace.path), "status", "--short")

    def diff(self, workspace: CodingWorkspace) -> str:
        return self._git(Path(workspace.path), "diff", "--")

    def run_tests(self, workspace: CodingWorkspace, args: list[str] | None = None, *, timeout: int = 180) -> dict[str, Any]:
        cmd = ["python", "-m", "pytest", *(args or ["-q"])]
        proc = subprocess.run(cmd, cwd=workspace.path, capture_output=True, text=True, timeout=timeout, shell=False)
        return {"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": proc.stdout[-20000:], "stderr": proc.stderr[-10000:]}

    def merge_plan(self, workspace: CodingWorkspace) -> dict[str, str]:
        return {"repo": workspace.repo, "branch": workspace.branch, "command": f"git -C {workspace.repo} merge --no-ff {workspace.branch}"}

    def remove(self, workspace: CodingWorkspace, *, delete_branch: bool = False) -> None:
        repo = Path(workspace.repo)
        self._git(repo, "worktree", "remove", "--force", workspace.path, timeout=120)
        if delete_branch:
            self._git(repo, "branch", "-D", workspace.branch)
