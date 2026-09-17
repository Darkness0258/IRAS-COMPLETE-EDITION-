from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import re
from typing import Callable, Any

from .common import new_id, utc_now

_SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{1,80}$")


@dataclass
class CapabilityProposal:
    proposal_id: str
    name: str
    description: str
    source: str
    tests: str
    permission: str
    status: str = "proposed"
    created_at: str = ""
    test_result: str = ""


class CapabilityLearner:
    """Proposal/test/install flow. Generated skills never self-install."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.proposals = self.root / "proposals"
        self.installed = self.root / "installed"
        self.proposals.mkdir(parents=True, exist_ok=True)
        self.installed.mkdir(parents=True, exist_ok=True)

    def propose(self, *, name: str, description: str, source: str, tests: str = "", permission: str = "READ") -> CapabilityProposal:
        if not _SAFE_NAME.match(name):
            raise ValueError("Invalid capability name.")
        proposal = CapabilityProposal(new_id("cap_"), name, description[:4000], source, tests, permission.upper(), created_at=utc_now())
        self._save(proposal)
        return proposal

    def _path(self, proposal_id: str) -> Path:
        return self.proposals / f"{proposal_id}.json"

    def _save(self, proposal: CapabilityProposal) -> None:
        self._path(proposal.proposal_id).write_text(json.dumps(asdict(proposal), ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, proposal_id: str) -> CapabilityProposal:
        return CapabilityProposal(**json.loads(self._path(proposal_id).read_text(encoding="utf-8")))

    def test(self, proposal_id: str, sandbox_runner: Callable[[str, str], dict[str, Any]]) -> CapabilityProposal:
        p = self.load(proposal_id)
        result = sandbox_runner(p.source, p.tests)
        p.test_result = json.dumps(result, ensure_ascii=False, default=str)[:16000]
        p.status = "tested" if result.get("ok") else "test_failed"
        self._save(p)
        return p

    def approve_install(self, proposal_id: str, *, approved: bool) -> Path:
        if not approved:
            raise PermissionError("Human approval is required to install a learned capability.")
        p = self.load(proposal_id)
        if p.status != "tested":
            raise RuntimeError("Capability must pass sandbox testing before installation.")
        target = self.installed / f"{p.name}.py"
        target.write_text(p.source, encoding="utf-8")
        p.status = "installed"
        self._save(p)
        return target
