from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json
from pathlib import Path
from typing import Any, Callable

from .common import new_id, utc_now


@dataclass
class WorkflowStep:
    action: str
    arguments: dict[str, Any] = field(default_factory=dict)
    verify: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecordedWorkflow:
    workflow_id: str
    name: str
    steps: list[WorkflowStep]
    created_at: str = field(default_factory=utc_now)

    def as_dict(self):
        return {"workflow_id": self.workflow_id, "name": self.name,
                "steps": [asdict(s) for s in self.steps], "created_at": self.created_at}


class WorkflowRecorder:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._active_name: str | None = None
        self._steps: list[WorkflowStep] = []

    def begin(self, name: str) -> None:
        if self._active_name:
            raise RuntimeError("A workflow recording is already active.")
        self._active_name = name[:160]
        self._steps = []

    def record(self, action: str, arguments: dict[str, Any] | None = None, verify: dict[str, Any] | None = None) -> None:
        if not self._active_name:
            raise RuntimeError("No workflow recording is active.")
        self._steps.append(WorkflowStep(action=action, arguments=arguments or {}, verify=verify or {}))

    def finish(self) -> RecordedWorkflow:
        if not self._active_name:
            raise RuntimeError("No workflow recording is active.")
        wf = RecordedWorkflow(new_id("wf_"), self._active_name, list(self._steps))
        path = self.root / f"{wf.workflow_id}.json"
        path.write_text(json.dumps(wf.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._active_name = None
        self._steps = []
        return wf

    def load(self, workflow_id: str) -> RecordedWorkflow:
        data = json.loads((self.root / f"{workflow_id}.json").read_text(encoding="utf-8"))
        return RecordedWorkflow(data["workflow_id"], data["name"], [WorkflowStep(**s) for s in data["steps"]], data["created_at"])

    def replay(self, workflow_id: str, executor: Callable[[str, dict[str, Any]], Any]) -> list[Any]:
        wf = self.load(workflow_id)
        outputs = []
        for step in wf.steps:
            outputs.append(executor(step.action, dict(step.arguments)))
        return outputs
