from __future__ import annotations

import json
import os
import secrets
from contextlib import contextmanager
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import edge_tts
from fastapi import (
    FastAPI,
    Header,
    HTTPException,
)
from fastapi.middleware.cors import (
    CORSMiddleware,
)
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import (
    StaticFiles,
)
from pydantic import (
    BaseModel,
    Field,
)
import uvicorn

from iras import __version__
from iras.models import PermissionLevel
from iras.remote_protocol import IRAS_CLOUD_SERVICE_ID, REMOTE_PROTOCOL_VERSION
from iras.remote_access import action_permission, level_for_mode
from iras.device_bridge.remote_context import remote_command_context
from iras.cloud_bootstrap import (
    build_cloud_runtime,
    build_cloud_worker,
)
from iras.multitasking import (
    MultitaskManager,
    TaskMemoryView,
    format_parallel_result,
    parse_parallel_command,
)
from iras.config import Settings
from iras.voice.humanize import (
    speech_text,
)
from iras.voice.profiles import (
    get_profile,
)


settings = Settings.load()
runtime = build_cloud_runtime(
    settings
)

# A normal Lock is intentional here. StreamingResponse may resume a sync
# generator on different worker threads; unlike RLock, Lock can safely be
# released by a different worker thread after the generator resumes.
agent_lock = threading.Lock()
started_at = time.time()

app = FastAPI(
    title="IRAS Cloud",
    version=__version__,
    description=(
        "Online IRAS brain "
        "shared by web, Android, "
        "and Windows clients."
    ),
)

origins = (
    ["*"]
    if settings.cors_origins == "*"
    else [
        x.strip()
        for x in (
            settings
            .cors_origins
            .split(",")
        )
        if x.strip()
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=(
        False
        if origins == ["*"]
        else True
    ),
    allow_methods=[
        "GET",
        "POST",
        "OPTIONS",
    ],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Device-ID",
        "X-IRAS-Remote-Session-ID",
        "X-IRAS-Remote-Token",
        "Accept",
    ],
)


class ChatIn(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=12000,
    )
    device_id: str = Field(
        default="unknown",
        max_length=128,
    )


class ChatOut(BaseModel):
    response: str
    request_id: str
    model: str
    timing_ms: int
    model_ms: int
    tool_schema_count: int


class MultitaskIn(BaseModel):
    tasks: list[str] = Field(default_factory=list)


class TTSIn(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=6000,
    )


class DevicePairIn(BaseModel):
    device_id: str = Field(
        min_length=8,
        max_length=128,
    )
    display_name: str = Field(
        min_length=1,
        max_length=128,
    )
    platform: str = Field(
        min_length=1,
        max_length=128,
    )
    capabilities: list[str] = Field(
        default_factory=list,
    )
    app_version: str = Field(
        default="unknown",
        max_length=32,
    )
    remote_protocol: int = Field(
        default=0,
        ge=0,
        le=999,
    )


class DeviceCompleteIn(BaseModel):
    ok: bool
    result: Any = None
    error: str = Field(
        default="",
        max_length=8000,
    )


class RemoteSessionIn(BaseModel):
    device_id: str | None = Field(default=None, max_length=128)
    mode: str = Field(default="control", pattern="^(read_only|control|full)$")
    ttl_seconds: int = Field(default=1800, ge=60, le=43200)
    scopes: list[str] = Field(default_factory=lambda: ["windows"], max_length=64)


class RemoteInvokeIn(BaseModel):
    session_id: str = Field(min_length=16, max_length=128)
    action: str = Field(min_length=1, max_length=128)
    arguments: dict = Field(default_factory=dict)
    timeout: float = Field(default=45.0, ge=1.0, le=180.0)


def _authorized(
    authorization: str | None,
) -> None:
    token = settings.api_token

    if (
        not token
        or token
        == (
            "change-me-before-"
            "remote-use"
        )
    ):
        raise HTTPException(
            status_code=503,
            detail=(
                "IRAS_API_TOKEN is "
                "not configured on "
                "the server."
            ),
        )

    if authorization != (
        f"Bearer {token}"
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid IRAS "
                "access token."
            ),
        )


def _device_authorized(
    device_id: str | None,
    device_token: str | None,
) -> str:
    if (
        not device_id
        or not device_token
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Missing IRAS device credentials."
            ),
        )

    if not (
        runtime.device_bridge
        .authorize_device(
            device_id,
            device_token,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Invalid IRAS device credentials."
            ),
        )

    return device_id



def _remote_session_cap() -> int:
    try:
        return max(0, min(int(os.getenv("IRAS_REMOTE_SESSION_MAX_PERMISSION_LEVEL", "2")), 3))
    except ValueError:
        return 2


def _authorize_remote_session(session_id: str | None, token: str | None) -> dict | None:
    if not session_id and not token:
        return None
    if not session_id or not token:
        raise HTTPException(status_code=401, detail="Both IRAS remote session ID and token are required.")
    session = runtime.device_bridge.authorize_remote_session(session_id, token)
    if not session:
        raise HTTPException(status_code=401, detail="Remote session is invalid, expired, or revoked.")
    if int(session.get("max_permission") or 0) > _remote_session_cap():
        raise HTTPException(status_code=403, detail="Remote session exceeds this server's configured permission cap.")
    scopes = {str(item).strip().lower() for item in (session.get("scopes") or [])}
    if "windows" not in scopes:
        raise HTTPException(status_code=403, detail="Remote session does not include the windows scope.")
    return session


@contextmanager
def _remote_permission_scope(session: dict | None, permissions=None):
    permissions = permissions or runtime.registry.permissions
    old_auto = permissions.auto_level
    old_cap = permissions.hard_cap
    old_confirm = permissions.always_confirm_critical
    try:
        if session:
            level = PermissionLevel(
                max(
                    0,
                    min(
                        int(session.get("max_permission") or 0),
                        _remote_session_cap(),
                    ),
                )
            )
            permissions.auto_level = level
            permissions.hard_cap = level
            permissions.always_confirm_critical = False
        # Device targeting is carried by ContextVar, not mutable global state.
        # This is essential when two parallel tasks use different sessions.
        with remote_command_context(session):
            yield
    finally:
        permissions.auto_level = old_auto
        permissions.hard_cap = old_cap
        permissions.always_confirm_critical = old_confirm


def _multitask_worker(prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    task_memory = TaskMemoryView(
        runtime.memory,
        seed_messages=context.get("seed_messages") or [],
    )
    worker = build_cloud_worker(runtime, task_memory)
    remote_session = context.get("remote_session")
    requester_device = str(context.get("requester_device") or "cloud-agent")[:128]
    started = time.perf_counter()
    try:
        with _remote_permission_scope(
            remote_session,
            worker.registry.permissions,
        ):
            result = worker.agent.handle(prompt)
        metrics = dict(worker.agent.last_metrics or {})
        metrics.setdefault(
            "total_ms",
            int((time.perf_counter() - started) * 1000),
        )

        # Commit completed task turns only after the isolated worker finishes.
        # Sibling workers keep their original context snapshot.
        runtime.memory.add_message(
            "user",
            "[Parallel task] " + prompt,
        )
        runtime.memory.add_message(
            "assistant",
            "[Parallel task result] " + str(result),
        )
        runtime.audit.record(
            "multitask_worker_complete",
            {
                "requester_device": requester_device,
                "remote_session_id": (remote_session or {}).get("session_id"),
                "prompt": prompt[:500],
                "total_ms": int(metrics.get("total_ms") or 0),
            },
        )
        return {
            "result": str(result),
            "metrics": metrics,
        }
    finally:
        worker.close()


multitask_manager = MultitaskManager(_multitask_worker)


def _multitask_context(
    *,
    remote_session: dict | None,
    requester_device: str,
) -> dict[str, Any]:
    try:
        history_limit = max(2, int(os.getenv("IRAS_CONTEXT_MESSAGES", "8")))
    except ValueError:
        history_limit = 8
    return {
        "remote_session": dict(remote_session) if remote_session else None,
        "requester_device": str(requester_device or "cloud-agent")[:128],
        "seed_messages": runtime.memory.recent_messages(history_limit),
    }


def _start_multitask(
    tasks: list[str],
    *,
    remote_session: dict | None,
    requester_device: str,
) -> dict[str, Any]:
    run = multitask_manager.submit(
        tasks,
        context=_multitask_context(
            remote_session=remote_session,
            requester_device=requester_device,
        ),
        requester_device=requester_device,
    )
    runtime.audit.record(
        "multitask_run_started",
        {
            "run_id": run["run_id"],
            "task_count": run["task_count"],
            "requester_device": requester_device,
            "remote_session_id": (remote_session or {}).get("session_id"),
        },
    )
    return run


def _sse(
    event: str,
    payload: dict,
) -> str:
    return (
        f"event: {event}\n"
        "data: "
        + json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n\n"
    )


@app.get("/health")
def health():
    """Render deployment liveness probe.

    Keep this endpoint dependency-free and fast: Render requires an HTTP health
    check response within five seconds during deploys. Rich provider/database
    diagnostics belong on /ready and must never gate port detection.
    """
    return {
        "ok": True,
        "service": "IRAS Cloud",
        "service_id": IRAS_CLOUD_SERVICE_ID,
        "version": __version__,
        "remote_protocol": REMOTE_PROTOCOL_VERSION,
        "uptime_seconds": int(time.time() - started_at),
    }


@app.get("/ready")
def readiness():
    """Detailed runtime status for diagnostics; not used as Render's health gate."""
    profile = get_profile(settings.voice_profile)
    return {
        "ok": True,
        "service": "IRAS Cloud",
        "version": __version__,
        "provider": settings.provider,
        "model": (
            getattr(runtime.agent.provider, "last_model", None)
            or settings.model
        ),
        "active_ai_provider": getattr(
            runtime.agent.provider,
            "last_provider",
            settings.provider,
        ),
        "ai_providers": (
            runtime.agent.provider.status()
            if callable(getattr(runtime.agent.provider, "status", None))
            else [{
                "name": settings.provider,
                "model": settings.model,
                "ready": True,
                "cooldown_seconds": 0,
            }]
        ),
        "database": "postgres" if settings.database_url else "sqlite-local",
        "voice_profile": settings.voice_profile,
        "voice": profile.voice,
        "streaming": True,
        "multitasking": {
            "enabled": True,
            "workers": multitask_manager.max_workers,
            "max_tasks_per_run": multitask_manager.max_tasks_per_run,
        },
        "latency_optimization": {
            "smart_tools": os.getenv("IRAS_SMART_TOOLS", "true"),
            "context_messages": os.getenv("IRAS_CONTEXT_MESSAGES", "8"),
            "context_facts": os.getenv("IRAS_CONTEXT_FACTS", "10"),
            "provider_sort": os.getenv("IRAS_PROVIDER_SORT", "latency"),
        },
        "uptime_seconds": int(time.time() - started_at),
    }


@app.post("/v1/multitask/runs")
def create_multitask_run(
    body: MultitaskIn,
    authorization: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
    x_iras_remote_session_id: str | None = Header(
        default=None, alias="X-IRAS-Remote-Session-ID"
    ),
    x_iras_remote_token: str | None = Header(
        default=None, alias="X-IRAS-Remote-Token"
    ),
):
    _authorized(authorization)
    remote_session = _authorize_remote_session(
        x_iras_remote_session_id,
        x_iras_remote_token,
    )
    requester = str(x_device_id or "web")[:128]
    try:
        return _start_multitask(
            body.tasks,
            remote_session=remote_session,
            requester_device=requester,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/multitask/runs/{run_id}")
def get_multitask_run(
    run_id: str,
    authorization: str | None = Header(default=None),
):
    _authorized(authorization)
    run = multitask_manager.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Multitask run not found.")
    return run


@app.delete("/v1/multitask/runs/{run_id}")
def cancel_multitask_run(
    run_id: str,
    authorization: str | None = Header(default=None),
):
    _authorized(authorization)
    run = multitask_manager.cancel(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Multitask run not found.")
    return run


@app.post(
    "/v1/chat",
    response_model=ChatOut,
)
def chat(
    body: ChatIn,
    authorization: str | None = Header(
        default=None
    ),
    x_device_id: str | None = Header(
        default=None
    ),
    x_iras_remote_session_id: str | None = Header(default=None, alias="X-IRAS-Remote-Session-ID"),
    x_iras_remote_token: str | None = Header(default=None, alias="X-IRAS-Remote-Token"),
):
    _authorized(authorization)
    remote_session = _authorize_remote_session(
        x_iras_remote_session_id,
        x_iras_remote_token,
    )

    request_id = (
        uuid.uuid4()
        .hex[:16]
    )

    device_id = (
        x_device_id
        or body.device_id
        or "unknown"
    )[:128]

    runtime.audit.record(
        "cloud_chat_request",
        {
            "request_id": (
                request_id
            ),
            "device_id": device_id,
            "stream": False,
            "remote_session_id": (remote_session or {}).get("session_id"),
        },
    )

    try:
        parallel_tasks = parse_parallel_command(body.message)
        if parallel_tasks:
            run = _start_multitask(
                parallel_tasks,
                remote_session=remote_session,
                requester_device=device_id,
            )
            run = multitask_manager.wait(
                run["run_id"],
                timeout=float(os.getenv("IRAS_MULTITASK_WAIT_TIMEOUT", "300")),
            )
            response = format_parallel_result(run)
            metrics = {
                "model": "parallel-task-supervisor",
                "total_ms": max(
                    [
                        int((task.get("metrics") or {}).get("total_ms") or 0)
                        for task in run.get("tasks") or []
                    ]
                    or [0]
                ),
                "model_ms": 0,
                "tool_schema_count": 0,
            }
        else:
            with agent_lock:
                with _remote_permission_scope(remote_session):
                    response = runtime.agent.handle(body.message)
            metrics = runtime.agent.last_metrics or {}

    except Exception as exc:
        print(
            "[IRAS CHAT ERROR] "
            f"{type(exc).__name__}: "
            f"{exc}",
            flush=True,
        )

        runtime.audit.record(
            "cloud_chat_error",
            {
                "request_id": (
                    request_id
                ),
                "error": repr(exc),
            },
        )

        if (
            "LLM HTTP 429" in str(exc)
            or "ALL_PROVIDERS_UNAVAILABLE" in str(exc)
        ):
            raise HTTPException(
                status_code=429,
                detail=(
                    "All configured AI providers are temporarily "
                    "unavailable or rate-limited. IRAS will automatically "
                    "try them again on your next message."
                ),
            ) from exc

        raise HTTPException(
            status_code=500,
            detail=(
                "IRAS could not "
                "complete this request."
            ),
        ) from exc

    return ChatOut(
        response=response,
        request_id=request_id,
        model=(
            metrics.get("model")
            or settings.model
        ),
        timing_ms=int(
            metrics.get(
                "total_ms",
                0,
            )
        ),
        model_ms=int(
            metrics.get(
                "model_ms",
                0,
            )
        ),
        tool_schema_count=int(
            metrics.get(
                "tool_schema_count",
                0,
            )
        ),
    )


@app.post("/v1/chat/stream")
def chat_stream(
    body: ChatIn,
    authorization: str | None = Header(
        default=None
    ),
    x_device_id: str | None = Header(
        default=None
    ),
    x_iras_remote_session_id: str | None = Header(default=None, alias="X-IRAS-Remote-Session-ID"),
    x_iras_remote_token: str | None = Header(default=None, alias="X-IRAS-Remote-Token"),
):
    """
    SSE streaming endpoint.

    Normal conversational turns stream token-by-token from OpenRouter.
    Tool-bearing turns preserve the existing agent/tool loop and deliver
    the completed tool result through the same SSE protocol.
    """
    _authorized(authorization)
    remote_session = _authorize_remote_session(
        x_iras_remote_session_id,
        x_iras_remote_token,
    )

    request_id = (
        uuid.uuid4()
        .hex[:16]
    )

    device_id = (
        x_device_id
        or body.device_id
        or "unknown"
    )[:128]

    parallel_tasks = parse_parallel_command(body.message)
    direct_stream = (
        False
        if parallel_tasks
        else runtime.agent.can_stream(body.message)
    )

    runtime.audit.record(
        "cloud_chat_request",
        {
            "request_id": request_id,
            "device_id": device_id,
            "stream": True,
            "direct_stream": (
                direct_stream
            ),
            "remote_session_id": (remote_session or {}).get("session_id"),
        },
    )

    def events():
        yield _sse(
            "start",
            {
                "request_id": (
                    request_id
                ),
                "streaming": (
                    direct_stream
                ),
            },
        )

        acquired = False

        try:
            if parallel_tasks:
                run = _start_multitask(
                    parallel_tasks,
                    remote_session=remote_session,
                    requester_device=device_id,
                )
                yield _sse(
                    "queued",
                    {
                        "request_id": request_id,
                        "message": (
                            f"IRAS started {len(parallel_tasks)} parallel tasks."
                        ),
                        "run_id": run["run_id"],
                        "waited_ms": 0,
                    },
                )
                wait_started = time.perf_counter()
                timeout = max(
                    30.0,
                    min(
                        float(os.getenv("IRAS_MULTITASK_WAIT_TIMEOUT", "300")),
                        600.0,
                    ),
                )
                deadline = time.monotonic() + timeout
                last_completed = -1
                while time.monotonic() < deadline:
                    snapshot = multitask_manager.get(run["run_id"])
                    if snapshot is None:
                        raise RuntimeError("Multitask run disappeared.")
                    completed = int(snapshot.get("completed_count") or 0)
                    if completed != last_completed:
                        last_completed = completed
                        yield _sse(
                            "queued",
                            {
                                "request_id": request_id,
                                "message": (
                                    f"Parallel progress: {completed}/{snapshot.get('task_count', 0)} tasks complete."
                                ),
                                "run_id": run["run_id"],
                                "waited_ms": int(
                                    (time.perf_counter() - wait_started) * 1000
                                ),
                            },
                        )
                    if snapshot.get("state") in {
                        "succeeded",
                        "partial_failure",
                        "cancelled",
                    }:
                        run = snapshot
                        break
                    time.sleep(0.20)
                else:
                    run = multitask_manager.get(run["run_id"]) or run

                text = format_parallel_result(run)
                yield _sse("token", {"text": text})
                total_ms = int((time.perf_counter() - wait_started) * 1000)
                yield _sse(
                    "done",
                    {
                        "request_id": request_id,
                        "model": "parallel-task-supervisor",
                        "timing_ms": total_ms,
                        "model_ms": 0,
                        "first_token_ms": total_ms,
                        "tool_schema_count": 0,
                        "streamed": False,
                        "queue_wait_ms": 0,
                        "parallel_run_id": run.get("run_id"),
                    },
                )
                return
            try:
                queue_wait = float(
                    os.getenv(
                        "IRAS_CHAT_QUEUE_TIMEOUT",
                        "180",
                    )
                )
            except ValueError:
                queue_wait = 180.0

            queue_wait = max(
                15.0,
                min(
                    queue_wait,
                    300.0,
                ),
            )

            queue_started = time.perf_counter()
            acquired = agent_lock.acquire(
                blocking=False
            )

            if not acquired:
                yield _sse(
                    "queued",
                    {
                        "request_id": request_id,
                        "message": (
                            "IRAS is finishing the previous request. "
                            "Your request is queued."
                        ),
                        "queue_timeout_ms": int(queue_wait * 1000),
                    },
                )

                runtime.audit.record(
                    "cloud_chat_queued",
                    {
                        "request_id": request_id,
                        "device_id": device_id,
                        "queue_timeout_ms": int(queue_wait * 1000),
                    },
                )

                deadline = time.perf_counter() + queue_wait
                while not acquired:
                    remaining = deadline - time.perf_counter()
                    if remaining <= 0:
                        break
                    acquired = agent_lock.acquire(
                        timeout=min(5.0, remaining)
                    )
                    if not acquired:
                        waited_ms = int(
                            (time.perf_counter() - queue_started) * 1000
                        )
                        yield _sse(
                            "queued",
                            {
                                "request_id": request_id,
                                "message": (
                                    "IRAS is still working on the previous request. "
                                    "This request remains queued."
                                ),
                                "waited_ms": waited_ms,
                                "queue_timeout_ms": int(queue_wait * 1000),
                            },
                        )

            queue_wait_ms = int(
                (time.perf_counter() - queue_started) * 1000
            )

            if not acquired:
                raise RuntimeError(
                    "IRAS request queue timed out while waiting for "
                    "the previous request to finish."
                )

            if queue_wait_ms >= 50:
                print(
                    "[IRAS QUEUE] "
                    f"waited={queue_wait_ms}ms request_id={request_id}",
                    flush=True,
                )

            if not direct_stream:
                # Tool-bearing turns are internally buffered and produce one
                # final response. Complete that work under the global agent
                # lock, copy metrics, then release the lock BEFORE yielding SSE
                # data so a slow/aborted client cannot pin the agent.
                try:
                    with _remote_permission_scope(remote_session):
                        tool_text = runtime.agent.handle(body.message)
                    metrics = dict(
                        runtime.agent.last_metrics
                        or {}
                    )
                finally:
                    if acquired:
                        agent_lock.release()
                        acquired = False

                if tool_text:
                    yield _sse(
                        "token",
                        {
                            "text": tool_text,
                        },
                    )

            else:
                # Ordinary no-tool conversation keeps true token streaming.
                try:
                    with _remote_permission_scope(remote_session):
                        for text in runtime.agent.handle_stream(body.message):
                            yield _sse(
                                "token",
                                {
                                    "text": text,
                                },
                            )
                finally:
                    if acquired:
                        agent_lock.release()
                        acquired = False

                metrics = dict(
                    runtime.agent.last_metrics
                    or {}
                )

            yield _sse(
                "done",
                {
                    "request_id": (
                        request_id
                    ),
                    "model": (
                        metrics.get(
                            "model"
                        )
                        or settings.model
                    ),
                    "timing_ms": int(
                        metrics.get(
                            "total_ms",
                            0,
                        )
                    ),
                    "model_ms": int(
                        metrics.get(
                            "model_ms",
                            0,
                        )
                    ),
                    "first_token_ms": int(
                        metrics.get(
                            "first_token_ms",
                            0,
                        )
                    ),
                    "tool_schema_count": int(
                        metrics.get(
                            "tool_schema_count",
                            0,
                        )
                    ),
                    "streamed": bool(
                        metrics.get(
                            "streamed",
                            False,
                        )
                    ),
                    "queue_wait_ms": queue_wait_ms,
                },
            )

        except GeneratorExit:
            raise

        except Exception as exc:
            print(
                "[IRAS STREAM ERROR] "
                f"{type(exc).__name__}: "
                f"{exc}",
                flush=True,
            )

            runtime.audit.record(
                "cloud_chat_error",
                {
                    "request_id": (
                        request_id
                    ),
                    "error": repr(exc),
                    "stream": True,
                },
            )

            error_text = str(exc)

            if (
                "request queue timed out" in error_text.lower()
                or "still finishing a previous request" in error_text
            ):
                user_message = (
                    "IRAS is handling a long-running request and the "
                    "queue wait limit was reached. Try again in a moment."
                )
                error_code = "request_busy"
            elif (
                "LLM HTTP 429" in error_text
                or "ALL_PROVIDERS_UNAVAILABLE" in error_text
            ):
                user_message = (
                    "All configured AI providers are temporarily "
                    "unavailable or rate-limited. IRAS will automatically "
                    "try them again on your next message."
                )
                error_code = "ai_rate_limited"
            else:
                user_message = (
                    "IRAS could not complete this request."
                )
                error_code = "request_failed"

            yield _sse(
                "error",
                {
                    "request_id": (
                        request_id
                    ),
                    "code": error_code,
                    "message": user_message,
                },
            )

    return StreamingResponse(
        events(),
        media_type=(
            "text/event-stream"
        ),
        headers={
            "Cache-Control": (
                "no-cache, no-transform"
            ),
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/v1/tts")
async def tts(
    body: TTSIn,
    authorization: str | None = Header(
        default=None
    ),
):
    _authorized(
        authorization
    )

    clean_text = speech_text(
        body.text
    )

    if not clean_text:
        raise HTTPException(
            status_code=400,
            detail=(
                "Nothing suitable "
                "to speak."
            ),
        )

    profile = get_profile(
        settings.voice_profile
    )

    try:
        communicate = (
            edge_tts.Communicate(
                clean_text,
                profile.voice,
                rate=profile.rate,
                volume=profile.volume,
                pitch=profile.pitch,
            )
        )

        audio = bytearray()

        async for chunk in (
            communicate.stream()
        ):
            if (
                chunk["type"]
                == "audio"
            ):
                audio.extend(
                    chunk["data"]
                )

        if not audio:
            raise RuntimeError(
                "Edge TTS returned "
                "no audio."
            )

        return Response(
            content=bytes(audio),
            media_type="audio/mpeg",
            headers={
                "Cache-Control": (
                    "no-store"
                ),
                "X-IRAS-Voice": (
                    profile.voice
                ),
                (
                    "X-IRAS-"
                    "Voice-Profile"
                ): (
                    settings
                    .voice_profile
                ),
            },
        )

    except Exception as exc:
        print(
            "[IRAS TTS ERROR] "
            f"{type(exc).__name__}: "
            f"{exc}",
            flush=True,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "IRAS voice "
                "generation failed."
            ),
        ) from exc




@app.post("/v1/devices/pair")
def pair_device(
    body: DevicePairIn,
    authorization: str | None = Header(
        default=None
    ),
):
    # Pairing requires the existing normal user API token.
    _authorized(authorization)
    if body.remote_protocol != REMOTE_PROTOCOL_VERSION:
        raise HTTPException(
            status_code=409,
            detail=(
                "IRAS Windows bridge remote protocol is incompatible "
                f"(client={body.remote_protocol}, server={REMOTE_PROTOCOL_VERSION}). "
                "Update the Windows IRAS package and redeploy the matching cloud release."
            ),
        )

    device_token = secrets.token_urlsafe(32)

    device = (
        runtime.device_bridge
        .pair_device(
            device_id=body.device_id,
            display_name=body.display_name,
            platform=body.platform,
            device_token=device_token,
            capabilities=[
                str(item)[:64]
                for item in body.capabilities[:64]
            ],
            app_version=body.app_version,
        )
    )

    runtime.audit.record(
        "device_paired",
        {
            "device_id": body.device_id,
            "display_name": body.display_name,
        },
    )

    return {
        "ok": True,
        "device": device,
        "device_token": device_token,
        "cloud_version": __version__,
        "remote_protocol": REMOTE_PROTOCOL_VERSION,
    }


@app.get("/v1/devices")
def list_devices(
    authorization: str | None = Header(
        default=None
    ),
):
    _authorized(authorization)

    return {
        "devices": (
            runtime.device_bridge
            .list_devices()
        )
    }


@app.get("/v1/devices/{device_id}/commands")
def device_command_history(
    device_id: str,
    authorization: str | None = Header(
        default=None
    ),
    limit: int = 20,
):
    _authorized(authorization)

    if not runtime.device_bridge.get_device(device_id):
        raise HTTPException(
            status_code=404,
            detail="Unknown IRAS device.",
        )

    return {
        "commands": (
            runtime.device_bridge
            .recent_commands(
                device_id,
                limit,
            )
        )
    }


@app.get("/v1/device/commands/next")
def device_next_command(
    timeout: int = 25,
    x_iras_device_id: str | None = Header(
        default=None,
        alias="X-IRAS-Device-ID",
    ),
    x_iras_device_token: str | None = Header(
        default=None,
        alias="X-IRAS-Device-Token",
    ),
):
    device_id = _device_authorized(
        x_iras_device_id,
        x_iras_device_token,
    )

    timeout = max(
        1,
        min(int(timeout), 30),
    )

    runtime.device_bridge.touch_device(device_id)
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        command = (
            runtime.device_bridge
            .claim_next(device_id)
        )

        if command:
            return {
                "command": command,
            }

        time.sleep(0.25)

    runtime.device_bridge.touch_device(device_id)

    return {
        "command": None,
    }


@app.post(
    "/v1/device/commands/{command_id}/complete"
)
def device_complete_command(
    command_id: str,
    body: DeviceCompleteIn,
    x_iras_device_id: str | None = Header(
        default=None,
        alias="X-IRAS-Device-ID",
    ),
    x_iras_device_token: str | None = Header(
        default=None,
        alias="X-IRAS-Device-Token",
    ),
):
    device_id = _device_authorized(
        x_iras_device_id,
        x_iras_device_token,
    )

    result = (
        runtime.device_bridge
        .complete(
            command_id=command_id,
            device_id=device_id,
            ok=body.ok,
            result=body.result,
            error=body.error,
        )
    )

    runtime.device_bridge.touch_device(device_id)

    runtime.audit.record(
        "device_command_complete",
        {
            "command_id": command_id,
            "device_id": device_id,
            "ok": body.ok,
        },
    )

    return {
        "ok": True,
        "command": result,
    }


@app.post("/v1/remote/sessions")
def create_remote_session(
    body: RemoteSessionIn,
    authorization: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None, alias="X-Device-ID"),
):
    _authorized(authorization)
    requested_level = level_for_mode(body.mode)
    if requested_level is None:
        raise HTTPException(status_code=400, detail="Invalid remote session mode.")
    if int(requested_level) > _remote_session_cap():
        raise HTTPException(
            status_code=403,
            detail=(
                f"Server remote-session cap is {PermissionLevel(_remote_session_cap()).name}; "
                f"requested mode {body.mode} requires {requested_level.name}."
            ),
        )
    session = runtime.device_bridge.create_remote_session(
        device_id=body.device_id,
        mode=body.mode,
        ttl_seconds=body.ttl_seconds,
        scopes=body.scopes,
        requester_device=x_device_id or "web",
    )
    runtime.audit.record(
        "remote_session_created",
        {
            "session_id": session["session_id"],
            "device_id": session["device_id"],
            "mode": session["mode"],
            "ttl_seconds": session["ttl_seconds"],
        },
    )
    return session


@app.get("/v1/remote/sessions")
def remote_sessions(authorization: str | None = Header(default=None)):
    _authorized(authorization)
    return {"sessions": runtime.device_bridge.list_remote_sessions()}


@app.delete("/v1/remote/sessions/{session_id}")
def revoke_remote_session(session_id: str, authorization: str | None = Header(default=None)):
    _authorized(authorization)
    revoked = runtime.device_bridge.revoke_remote_session(session_id)
    runtime.audit.record("remote_session_revoked", {"session_id": session_id, "revoked": revoked})
    return {"ok": True, "revoked": revoked}


@app.post("/v1/remote/invoke")
def remote_invoke(
    body: RemoteInvokeIn,
    x_iras_remote_token: str | None = Header(default=None, alias="X-IRAS-Remote-Token"),
    x_device_id: str | None = Header(default=None, alias="X-Device-ID"),
):
    session = _authorize_remote_session(body.session_id, x_iras_remote_token)
    assert session is not None
    required = action_permission(body.action, body.arguments)
    if int(required) > int(session.get("max_permission") or 0):
        raise HTTPException(status_code=403, detail=f"Remote session does not authorize {required.name} actions.")
    try:
        result = runtime.device_bridge.remote_request_and_wait(
            session=session,
            action=body.action,
            arguments=body.arguments,
            timeout=body.timeout,
            requester_device=x_device_id or "remote-client",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    runtime.audit.record(
        "remote_direct_invoke",
        {
            "session_id": session.get("session_id"),
            "device_id": session.get("device_id"),
            "action": body.action,
            "permission": required.name,
        },
    )
    return {"ok": True, "result": result}


@app.get("/v1/personality")
def personality(
    authorization: str | None = Header(
        default=None
    ),
):
    _authorized(
        authorization
    )

    return (
        runtime.personality
        .status()
    )


@app.post(
    "/v1/personality/reset"
)
def personality_reset(
    authorization: str | None = Header(
        default=None
    ),
):
    _authorized(
        authorization
    )

    return {
        "ok": True,
        "state": (
            runtime.personality
            .reset()
        ),
    }


@app.get("/v1/tools")
def tools(
    authorization: str | None = Header(
        default=None
    ),
):
    _authorized(
        authorization
    )

    return (
        runtime.registry
        .describe()
    )


_web_candidates = [
    (
        Path(__file__)
        .resolve()
        .parents[3]
        / "clients"
        / "web"
    ),
    (
        Path.cwd()
        / "clients"
        / "web"
    ),
]

web_dir = next(
    (
        path
        for path in (
            _web_candidates
        )
        if path.exists()
    ),
    None,
)

if web_dir:
    app.mount(
        "/app",
        StaticFiles(
            directory=web_dir,
            html=True,
        ),
        name="webapp",
    )

    @app.get("/")
    def home():
        return FileResponse(
            web_dir
            / "index.html"
        )

else:

    @app.get("/")
    def home():
        return JSONResponse(
            {
                "service": (
                    "IRAS Cloud"
                ),
                "version": (
                    __version__
                ),
                "app": "/app/",
                "health": "/health",
            }
        )


@app.on_event("shutdown")
def shutdown_event():
    provider = runtime.agent.provider

    provider_close = getattr(
        provider,
        "close",
        None,
    )

    if callable(provider_close):
        provider_close()

    memory_close = getattr(
        runtime.memory,
        "close",
        None,
    )

    if callable(memory_close):
        memory_close()

    bridge_close = getattr(
        runtime.device_bridge,
        "close",
        None,
    )

    if callable(bridge_close):
        bridge_close()


def main():
    port = int(
        os.getenv(
            "PORT",
            "10000",
        )
    )

    print(
        f"[IRAS CLOUD] binding 0.0.0.0:{port}",
        flush=True,
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
