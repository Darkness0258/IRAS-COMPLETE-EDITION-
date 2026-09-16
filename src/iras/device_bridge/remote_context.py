from __future__ import annotations

"""Per-request provenance for remote Windows tool delivery.

The cloud agent is shared, so remote-session metadata must not live in mutable
module globals. Context variables follow the current request/tool execution and
allow device commands created by ordinary chat tools to remain bound to the
session that authorized them.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


_session_id: ContextVar[str] = ContextVar("iras_remote_session_id", default="")
_requester: ContextVar[str] = ContextVar("iras_remote_requester", default="cloud-agent")
_device_id: ContextVar[str] = ContextVar("iras_remote_device_id", default="")


@dataclass(frozen=True, slots=True)
class RemoteCommandContext:
    session_id: str = ""
    requester_device: str = "cloud-agent"
    device_id: str = ""


@contextmanager
def remote_command_context(session: dict | None) -> Iterator[RemoteCommandContext]:
    if not session:
        yield RemoteCommandContext()
        return
    sid = str(session.get("session_id") or "")
    requester = str(session.get("requester_device") or "remote-session")[:128]
    device_id = str(session.get("device_id") or "")[:128]
    token_sid = _session_id.set(sid)
    token_req = _requester.set(requester)
    token_device = _device_id.set(device_id)
    try:
        yield RemoteCommandContext(
            session_id=sid,
            requester_device=requester,
            device_id=device_id,
        )
    finally:
        _session_id.reset(token_sid)
        _requester.reset(token_req)
        _device_id.reset(token_device)


def current_remote_command_context() -> RemoteCommandContext:
    return RemoteCommandContext(
        session_id=_session_id.get(),
        requester_device=_requester.get(),
        device_id=_device_id.get(),
    )
