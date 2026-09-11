from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

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
from iras.cloud_bootstrap import (
    build_cloud_runtime,
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


class TTSIn(BaseModel):
    text: str = Field(
        min_length=1,
        max_length=6000,
    )


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
    profile = get_profile(
        settings.voice_profile
    )

    return {
        "ok": True,
        "service": "IRAS Cloud",
        "version": __version__,
        "provider": (
            settings.provider
        ),
        "model": (
            getattr(
                runtime.agent.provider,
                "last_model",
                None,
            )
            or settings.model
        ),
        "active_ai_provider": getattr(
            runtime.agent.provider,
            "last_provider",
            settings.provider,
        ),
        "ai_providers": (
            runtime.agent.provider.status()
            if callable(
                getattr(
                    runtime.agent.provider,
                    "status",
                    None,
                )
            )
            else [
                {
                    "name": settings.provider,
                    "model": settings.model,
                    "ready": True,
                    "cooldown_seconds": 0,
                }
            ]
        ),
        "database": (
            "postgres"
            if settings.database_url
            else "sqlite-local"
        ),
        "voice_profile": (
            settings.voice_profile
        ),
        "voice": profile.voice,
        "streaming": True,
        "latency_optimization": {
            "smart_tools": (
                os.getenv(
                    "IRAS_SMART_TOOLS",
                    "true",
                )
            ),
            "context_messages": (
                os.getenv(
                    "IRAS_CONTEXT_MESSAGES",
                    "8",
                )
            ),
            "context_facts": (
                os.getenv(
                    "IRAS_CONTEXT_FACTS",
                    "10",
                )
            ),
            "provider_sort": (
                os.getenv(
                    "IRAS_PROVIDER_SORT",
                    "latency",
                )
            ),
        },
        "uptime_seconds": int(
            time.time()
            - started_at
        ),
    }


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
):
    _authorized(
        authorization
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
        },
    )

    try:
        with agent_lock:
            response = (
                runtime.agent.handle(
                    body.message
                )
            )

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

    metrics = (
        runtime.agent
        .last_metrics
        or {}
    )

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
):
    """
    SSE streaming endpoint.

    Normal conversational turns stream token-by-token from OpenRouter.
    Tool-bearing turns preserve the existing agent/tool loop and deliver
    the completed tool result through the same SSE protocol.
    """
    _authorized(
        authorization
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

    direct_stream = (
        runtime.agent.can_stream(
            body.message
        )
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

        try:
            agent_lock.acquire()

            try:
                for text in (
                    runtime.agent
                    .handle_stream(
                        body.message
                    )
                ):
                    yield _sse(
                        "token",
                        {
                            "text": text,
                        },
                    )
            finally:
                agent_lock.release()

            metrics = (
                runtime.agent
                .last_metrics
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


def main():
    port = int(
        os.getenv(
            "PORT",
            "8765",
        )
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
