from __future__ import annotations

"""Per-request provenance for remote Windows tool delivery.

The cloud agent is shared, so remote-session metadata and orchestration workspace
metadata must not live in mutable module globals. Context variables follow the
current request/tool execution and keep device commands bound to the session and
verified project root that authorized them.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


_session_id: ContextVar[str] = ContextVar("iras_remote_session_id", default="")
_requester: ContextVar[str] = ContextVar("iras_remote_requester", default="cloud-agent")
_device_id: ContextVar[str] = ContextVar("iras_remote_device_id", default="")
_project_root: ContextVar[str] = ContextVar("iras_remote_project_root", default="")


@dataclass(frozen=True, slots=True)
class RemoteCommandContext:
    session_id: str = ""
    requester_device: str = "cloud-agent"
    device_id: str = ""
    project_root: str = ""


@contextmanager
def remote_command_context(
    session: dict | None,
    *,
    project_root: str = "",
) -> Iterator[RemoteCommandContext]:
    sid = str((session or {}).get("session_id") or "")
    requester = str((session or {}).get("requester_device") or "remote-session")[:128] if session else "cloud-agent"
    device_id = str((session or {}).get("device_id") or "")[:128]
    workspace = str(project_root or "").strip()

    token_sid = _session_id.set(sid)
    token_req = _requester.set(requester)
    token_device = _device_id.set(device_id)
    token_project = _project_root.set(workspace)
    try:
        yield RemoteCommandContext(
            session_id=sid,
            requester_device=requester,
            device_id=device_id,
            project_root=workspace,
        )
    finally:
        _session_id.reset(token_sid)
        _requester.reset(token_req)
        _device_id.reset(token_device)
        _project_root.reset(token_project)


def current_remote_command_context() -> RemoteCommandContext:
    return RemoteCommandContext(
        session_id=_session_id.get(),
        requester_device=_requester.get(),
        device_id=_device_id.get(),
        project_root=_project_root.get(),
    )
