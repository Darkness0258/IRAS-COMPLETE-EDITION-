from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
import threading
import time
import uuid
from typing import Any, Callable

from iras.master_control import master_execution_limits_for_context


TERMINAL_STATES = {"succeeded", "failed", "cancelled"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


class TaskMemoryView:
    """Conversation-isolated view over IRAS durable memory.

    Parallel workers share durable facts, but each worker receives the same
    conversation snapshot and keeps its temporary user/assistant turns local.
    This prevents sibling tasks from seeing partially completed work from one
    another while still allowing intentional ``remember_fact`` writes.
    """

    def __init__(
        self,
        base,
        *,
        seed_messages: list[dict[str, Any]] | None = None,
    ):
        self.base = base
        self._lock = threading.RLock()
        self._seed_messages = [
            {
                "role": str(item.get("role") or ""),
                "content": str(item.get("content") or ""),
            }
            for item in (seed_messages or [])
            if isinstance(item, dict)
        ]
        self._local_messages: list[dict[str, str]] = []

    def add_message(self, role, content):
        with self._lock:
            self._local_messages.append(
                {
                    "role": str(role),
                    "content": str(content),
                }
            )

    def recent_messages(self, limit=20):
        limit = max(1, min(int(limit), 200))
        with self._lock:
            combined = [*self._seed_messages, *self._local_messages]
            return [dict(item) for item in combined[-limit:]]

    def remember(self, key, value):
        return self.base.remember(key, value)

    def get_fact(self, key, default=None):
        return self.base.get_fact(key, default)

    def search_facts(self, query, limit=10):
        return self.base.search_facts(query, limit)

    def all_facts(self, limit=100):
        return self.base.all_facts(limit)

    def local_messages(self) -> list[dict[str, str]]:
        with self._lock:
            return [dict(item) for item in self._local_messages]


@dataclass
class TaskRecord:
    task_id: str
    index: int
    prompt: str
    state: str = "queued"
    created_at: str = field(default_factory=_now_iso)
    started_at: str | None = None
    finished_at: str | None = None
    result: str = ""
    error: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    future: Future | None = field(default=None, repr=False, compare=False)

    def public(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "index": self.index,
            "prompt": self.prompt,
            "state": self.state,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
            "metrics": dict(self.metrics),
        }


@dataclass
class TaskRun:
    run_id: str
    tasks: list[TaskRecord]
    created_at: str = field(default_factory=_now_iso)
    finished_at: str | None = None
    requester_device: str = "cloud-agent"

    def public(self) -> dict[str, Any]:
        states = [task.state for task in self.tasks]
        if states and all(state in TERMINAL_STATES for state in states):
            if any(state == "failed" for state in states):
                state = "partial_failure"
            elif any(state == "cancelled" for state in states):
                state = "cancelled"
            else:
                state = "succeeded"
        elif any(state == "running" for state in states):
            state = "running"
        else:
            state = "queued"

        return {
            "run_id": self.run_id,
            "state": state,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "requester_device": self.requester_device,
            "task_count": len(self.tasks),
            "completed_count": sum(
                1 for task in self.tasks if task.state in TERMINAL_STATES
            ),
            "tasks": [task.public() for task in self.tasks],
        }


class MultitaskManager:
    """Bounded parallel job supervisor for independent IRAS agent workers."""

    def __init__(
        self,
        runner: Callable[[str, dict[str, Any]], dict[str, Any]],
        *,
        max_workers: int | None = None,
        max_tasks_per_run: int | None = None,
        retained_runs: int = 40,
    ):
        self.runner = runner
        self.max_workers = max_workers or _env_int(
            "IRAS_MULTITASK_WORKERS", 4, 1, 8
        )
        self.max_tasks_per_run = max_tasks_per_run or _env_int(
            "IRAS_MULTITASK_MAX_TASKS", 8, 2, 12
        )
        self.retained_runs = max(5, min(int(retained_runs), 200))
        self.max_active_runs_per_requester = _env_int(
            "IRAS_MULTITASK_MAX_ACTIVE_RUNS", 4, 1, 20
        )
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="iras-task",
        )
        self._lock = threading.RLock()
        self._runs: dict[str, TaskRun] = {}

    def _prune_locked(self) -> None:
        if len(self._runs) <= self.retained_runs:
            return
        terminal = [
            run
            for run in self._runs.values()
            if all(task.state in TERMINAL_STATES for task in run.tasks)
        ]
        terminal.sort(key=lambda item: item.created_at)
        while len(self._runs) > self.retained_runs and terminal:
            run = terminal.pop(0)
            self._runs.pop(run.run_id, None)

    @staticmethod
    def _normalize_prompts(prompts: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in prompts:
            text = " ".join(str(raw or "").strip().split())
            if not text:
                continue
            if len(text) > 12000:
                raise ValueError("Each parallel task must be 12,000 characters or fewer.")
            cleaned.append(text)
        return cleaned

    def submit(
        self,
        prompts: list[str],
        *,
        context: dict[str, Any] | None = None,
        requester_device: str = "cloud-agent",
    ) -> dict[str, Any]:
        prompts = self._normalize_prompts(prompts)
        if len(prompts) < 2:
            raise ValueError("Multitasking requires at least two tasks.")
        effective_max_tasks = self.max_tasks_per_run
        master_limits = master_execution_limits_for_context(context)
        if master_limits.get("active"):
            effective_max_tasks = max(
                effective_max_tasks, int(master_limits.get("parallel_tasks") or 128)
            )
        if len(prompts) > effective_max_tasks:
            raise ValueError(
                f"A multitask run supports at most {effective_max_tasks} tasks."
            )

        run_id = uuid.uuid4().hex[:16]
        run = TaskRun(
            run_id=run_id,
            requester_device=str(requester_device or "cloud-agent")[:128],
            tasks=[
                TaskRecord(
                    task_id=f"{run_id}-{index + 1}",
                    index=index + 1,
                    prompt=prompt,
                )
                for index, prompt in enumerate(prompts)
            ],
        )
        base_context = dict(context or {})

        with self._lock:
            active = sum(
                1 for item in self._runs.values()
                if item.requester_device == run.requester_device
                and not all(task.state in TERMINAL_STATES for task in item.tasks)
            )
            effective_active_runs = self.max_active_runs_per_requester
            master_limits = master_execution_limits_for_context(base_context)
            if master_limits.get("active"):
                effective_active_runs = max(
                    effective_active_runs, int(master_limits.get("active_runs") or 32)
                )
            if active >= effective_active_runs:
                raise RuntimeError(
                    f"Too many active parallel runs for {run.requester_device!r}; "
                    f"limit is {effective_active_runs}."
                )
            self._runs[run_id] = run
            self._prune_locked()
            for task in run.tasks:
                task.future = self._executor.submit(
                    self._execute,
                    run_id,
                    task.task_id,
                    task.prompt,
                    dict(base_context),
                )

        return run.public()

    def _execute(
        self,
        run_id: str,
        task_id: str,
        prompt: str,
        context: dict[str, Any],
    ) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            task = next((item for item in run.tasks if item.task_id == task_id), None)
            if not task or task.state == "cancelled":
                return
            task.state = "running"
            task.started_at = _now_iso()

        started = time.perf_counter()
        try:
            output = self.runner(prompt, context) or {}
            text = str(output.get("result") or "")
            metrics = dict(output.get("metrics") or {})
            with self._lock:
                task.result = text
                task.metrics = metrics
                task.state = "succeeded"
                task.finished_at = _now_iso()
        except Exception as exc:
            with self._lock:
                task.error = f"{type(exc).__name__}: {exc}"
                task.metrics = {
                    "total_ms": int((time.perf_counter() - started) * 1000)
                }
                task.state = "failed"
                task.finished_at = _now_iso()
        finally:
            with self._lock:
                run = self._runs.get(run_id)
                if run and all(item.state in TERMINAL_STATES for item in run.tasks):
                    run.finished_at = _now_iso()

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(str(run_id))
            return run.public() if run else None

    def cancel(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(str(run_id))
            if not run:
                return None
            for task in run.tasks:
                if task.state != "queued":
                    continue
                future = task.future
                if future is not None and future.cancel():
                    task.state = "cancelled"
                    task.finished_at = _now_iso()
            if all(item.state in TERMINAL_STATES for item in run.tasks):
                run.finished_at = _now_iso()
            return run.public()

    def wait(self, run_id: str, timeout: float = 300.0) -> dict[str, Any]:
        deadline = time.monotonic() + max(1.0, min(float(timeout), 600.0))
        while time.monotonic() < deadline:
            snapshot = self.get(run_id)
            if snapshot is None:
                raise KeyError(run_id)
            if snapshot["state"] in {"succeeded", "partial_failure", "cancelled"}:
                return snapshot
            time.sleep(0.10)
        snapshot = self.get(run_id)
        if snapshot is None:
            raise KeyError(run_id)
        return snapshot

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def parse_parallel_command(text: str) -> list[str]:
    """Parse explicit chat syntax without guessing how to split user intent.

    Examples:
      /parallel research X || inspect project Y || check PC status
      /multitask\nresearch X\ninspect Y\ncheck Z
    """

    raw = str(text or "").strip()
    lower = raw.lower()
    prefix = ""
    for candidate in ("/parallel", "/multitask"):
        if lower == candidate or lower.startswith(candidate + " ") or lower.startswith(candidate + "\n"):
            prefix = candidate
            break
    if not prefix:
        return []

    payload = raw[len(prefix):].strip()
    if not payload:
        return []

    if "||" in payload:
        parts = payload.split("||")
    else:
        parts = payload.splitlines()

    return [
        " ".join(part.strip().split())
        for part in parts
        if part.strip()
    ]


def format_parallel_result(run: dict[str, Any]) -> str:
    lines = [
        f"Parallel run {run.get('run_id', '')} finished: "
        f"{run.get('completed_count', 0)}/{run.get('task_count', 0)} tasks completed."
    ]
    for task in run.get("tasks") or []:
        index = task.get("index")
        prompt = str(task.get("prompt") or "")
        state = str(task.get("state") or "")
        if state == "succeeded":
            result = str(task.get("result") or "").strip() or "Completed."
            lines.append(f"\nTask {index} — {prompt}\n{result}")
        else:
            error = str(task.get("error") or state or "Task did not complete.")
            lines.append(f"\nTask {index} — {prompt}\nFailed: {error}")
    return "\n".join(lines).strip()
