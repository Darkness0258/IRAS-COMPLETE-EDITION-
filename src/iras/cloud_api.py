from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path

import edge_tts
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from iras import __version__
from iras.cloud_bootstrap import build_cloud_runtime
from iras.config import Settings
from iras.voice.humanize import speech_text
from iras.voice.profiles import get_profile

settings = Settings.load()
runtime = build_cloud_runtime(settings)
agent_lock = threading.RLock()
started_at = time.time()

app = FastAPI(
    title="IRAS Cloud",
    version=__version__,
    description="Online IRAS brain shared by web, Android, and Windows clients.",
)

origins = ["*"] if settings.cors_origins == "*" else [
    x.strip() for x in settings.cors_origins.split(",") if x.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False if origins == ["*"] else True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Device-ID"],
)

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    device_id: str = Field(default="unknown", max_length=128)

class ChatOut(BaseModel):
    response: str
    request_id: str
    model: str

class TTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=6000)

def _authorized(authorization: str | None) -> None:
    token = settings.api_token
    if not token or token == "change-me-before-remote-use":
        raise HTTPException(status_code=503, detail="IRAS_API_TOKEN is not configured on the server.")
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Invalid IRAS access token.")

@app.get("/health")
def health():
    profile = get_profile(settings.voice_profile)
    return {
        "ok": True,
        "service": "IRAS Cloud",
        "version": __version__,
        "provider": settings.provider,
        "model": settings.model,
        "database": "postgres" if settings.database_url else "sqlite-local",
        "voice_profile": settings.voice_profile,
        "voice": profile.voice,
        "uptime_seconds": int(time.time() - started_at),
    }

@app.post("/v1/chat", response_model=ChatOut)
def chat(
    body: ChatIn,
    authorization: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
):
    _authorized(authorization)
    request_id = uuid.uuid4().hex[:16]
    device_id = (x_device_id or body.device_id or "unknown")[:128]

    runtime.audit.record(
        "cloud_chat_request",
        {"request_id": request_id, "device_id": device_id},
    )

    try:
        with agent_lock:
            response = runtime.agent.handle(body.message)
    except Exception as exc:
<<<<<<< HEAD
        print(f"[IRAS CHAT ERROR] {type(exc).__name__}: {exc}", flush=True)
=======
        error_text = f"{type(exc).__name__}: {exc}"

        print(
            f"[IRAS CHAT ERROR] {error_text}",
            flush=True,
        )

>>>>>>> 77ccddaeae228a0c5093a53bd91bba9334aa3a7f
        runtime.audit.record(
            "cloud_chat_error",
            {"request_id": request_id, "error": repr(exc)},
        )
        raise HTTPException(
            status_code=500,
            detail=error_text,
        ) from exc

    return ChatOut(
        response=response,
        request_id=request_id,
        model=settings.model,
    )

@app.post("/v1/tts")
async def tts(
    body: TTSIn,
    authorization: str | None = Header(default=None),
):
    _authorized(authorization)

    clean_text = speech_text(body.text)
    if not clean_text:
        raise HTTPException(status_code=400, detail="Nothing suitable to speak.")

    profile = get_profile(settings.voice_profile)

    try:
        communicate = edge_tts.Communicate(
            clean_text,
            profile.voice,
            rate=profile.rate,
            volume=profile.volume,
            pitch=profile.pitch,
        )

        audio = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])

        if not audio:
            raise RuntimeError("Edge TTS returned no audio.")

        return Response(
            content=bytes(audio),
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "no-store",
                "X-IRAS-Voice": profile.voice,
                "X-IRAS-Voice-Profile": settings.voice_profile,
            },
        )
    except Exception as exc:
        print(f"[IRAS TTS ERROR] {type(exc).__name__}: {exc}", flush=True)
        raise HTTPException(
            status_code=502,
            detail="IRAS voice generation failed.",
        ) from exc

@app.get("/v1/personality")
def personality(authorization: str | None = Header(default=None)):
    _authorized(authorization)
    return runtime.personality.status()

@app.post("/v1/personality/reset")
def personality_reset(authorization: str | None = Header(default=None)):
    _authorized(authorization)
    return {"ok": True, "state": runtime.personality.reset()}

@app.get("/v1/tools")
def tools(authorization: str | None = Header(default=None)):
    _authorized(authorization)
    return runtime.registry.describe()

_web_candidates = [
    Path(__file__).resolve().parents[3] / "clients" / "web",
    Path.cwd() / "clients" / "web",
]

web_dir = next((path for path in _web_candidates if path.exists()), None)

if web_dir:
    app.mount("/app", StaticFiles(directory=web_dir, html=True), name="webapp")

    @app.get("/")
    def home():
        return FileResponse(web_dir / "index.html")
else:
    @app.get("/")
    def home():
        return JSONResponse({
            "service": "IRAS Cloud",
            "version": __version__,
            "app": "/app/",
            "health": "/health",
        })

def main():
    port = int(os.getenv("PORT", "8765"))
    uvicorn.run(
        "iras.cloud_api:app",
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )

if __name__ == "__main__":
    main()
