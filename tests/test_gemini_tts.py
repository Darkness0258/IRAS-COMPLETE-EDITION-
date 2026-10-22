import asyncio
import base64

import pytest
from aiohttp import web

from iras.voice import gemini_tts


def _run(coro):
    return asyncio.run(coro)


async def _with_server(handler, work):
    app = web.Application()
    app.router.add_post("/v1beta/interactions", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        return await work(f"http://127.0.0.1:{port}/v1beta/interactions")
    finally:
        await runner.cleanup()


def test_voice_choice(monkeypatch):
    monkeypatch.delenv("IRAS_TTS_ENGINE", raising=False)
    assert gemini_tts.voice_for("gemini_leda") == "Leda"
    assert gemini_tts.voice_for("gemini_voice_abc123") == "voice_abc123"
    assert gemini_tts.voice_for("iras_human") is None
    assert gemini_tts.voice_for("") is None
    monkeypatch.setenv("IRAS_TTS_ENGINE", "gemini")
    monkeypatch.setenv("IRAS_GEMINI_VOICE", "aoede")
    assert gemini_tts.voice_for("iras_human") == "Aoede"
    assert gemini_tts.voice_for(None) == "Aoede"
    assert gemini_tts.voice_for("anime_soft") is None  # an explicit Edge choice is kept


def test_synthesize_sends_the_documented_request_and_returns_the_wav(monkeypatch):
    seen = {}

    async def handler(request):
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = await request.json()
        wav = base64.b64encode(b"RIFFfakewav").decode()
        return web.json_response({"steps": [{"type": "model_output", "content": [{"type": "audio", "data": wav}]}]})

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("IRAS_GEMINI_STYLE", raising=False)
    monkeypatch.delenv("IRAS_GEMINI_TTS_MODEL", raising=False)

    async def work(url):
        monkeypatch.setenv("IRAS_GEMINI_TTS_URL", url)
        return await gemini_tts.synthesize("Hi there.", "Leda", mood="warm")

    assert _run(_with_server(handler, work)) == b"RIFFfakewav"
    body = seen["body"]
    assert seen["key"] == "test-key"
    assert body["model"] == "gemini-3.8-flash-lite-tts"
    assert body["response_format"] == {"type": "audio"}
    assert body["generation_config"]["speech_config"] == [{"voice": "Leda"}]
    block = body["input"][0]["content"][0]
    assert block["text"] == "Hi there."
    assert block["annotations"][0] == {"type": "speech_metadata", "style": "casual, warm and friendly"}


def test_errors_are_clear(monkeypatch):
    async def busy(request):
        return web.json_response({"error": {"message": "Quota exceeded"}}, status=429)

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    async def work(url):
        monkeypatch.setenv("IRAS_GEMINI_TTS_URL", url)
        with pytest.raises(RuntimeError, match="429.*Quota exceeded"):
            await gemini_tts.synthesize("Hi.", "Leda")

    _run(_with_server(busy, work))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        _run(gemini_tts.synthesize("Hi.", "Leda"))
