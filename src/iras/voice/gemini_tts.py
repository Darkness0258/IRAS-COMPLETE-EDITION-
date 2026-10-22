"""Natural speech from the Gemini API (gemini-3.8 TTS models).

POST /v1/tts uses this when the request asks for a profile that starts with
"gemini_" (for example "gemini_leda"), or for the default profile when the
server has IRAS_TTS_ENGINE=gemini. If anything goes wrong the caller falls
back to the Edge voices, so she never goes silent.

Settings (all optional, read from the environment):
  GEMINI_API_KEY        the same key the chat brain already uses
  IRAS_TTS_ENGINE       "gemini" makes it the default voice for every client
  IRAS_GEMINI_VOICE     default voice name, for example Leda, Aoede, Sulafat
  IRAS_GEMINI_TTS_MODEL default gemini-3.8-flash-lite-tts (fast); the
                        gemini-3.8-flash-tts model is richer but slower
  IRAS_GEMINI_STYLE     one short style phrase; empty turns styling off
"""
from __future__ import annotations

import base64
import os

import aiohttp

DEFAULT_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_MODEL = "gemini-3.8-flash-lite-tts"
DEFAULT_VOICE = "Leda"
_STYLES = {
    "warm": "casual, warm and friendly",
    "calm": "calm and gentle",
    "bright": "bright and cheerful",
    "neutral": "",
}


def api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()


def _clean_voice(name: str) -> str:
    name = (name or "").strip()
    if name.lower().startswith(("voice_", "voicekey_")):
        return name  # a custom voice made in Google's Voice design
    return name[:1].upper() + name[1:].lower() if name else DEFAULT_VOICE


def voice_for(requested_profile: str | None) -> str | None:
    """The Gemini voice to use for this request, or None to keep the Edge voice."""
    profile = str(requested_profile or "").strip()
    if profile.lower().startswith("gemini_"):
        return _clean_voice(profile[len("gemini_"):])
    engine = os.getenv("IRAS_TTS_ENGINE", "").strip().lower()
    if engine == "gemini" and profile.lower() in ("", "iras_human"):
        return _clean_voice(os.getenv("IRAS_GEMINI_VOICE", DEFAULT_VOICE))
    return None


async def synthesize(text: str, voice: str, mood: str | None = "warm", timeout: float = 30.0) -> bytes:
    """Return a WAV file (24 kHz, mono) of her saying `text`."""
    key = api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set on the server.")
    block: dict = {"type": "text", "text": text}
    custom = os.getenv("IRAS_GEMINI_STYLE")
    style = custom if custom is not None else _STYLES.get(str(mood or "warm").lower(), _STYLES["warm"])
    if style.strip():
        block["annotations"] = [{"type": "speech_metadata", "style": style.strip()}]
    payload = {
        "model": os.getenv("IRAS_GEMINI_TTS_MODEL", "").strip() or DEFAULT_MODEL,
        "input": [{"type": "user_input", "content": [block]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }
    url = os.getenv("IRAS_GEMINI_TTS_URL", "").strip() or DEFAULT_URL
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        async with session.post(url, json=payload, headers={"x-goog-api-key": key}) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = {}
            if resp.status != 200:
                err = data.get("error") if isinstance(data, dict) else None
                message = err.get("message") if isinstance(err, dict) else ""
                raise RuntimeError(f"Gemini voice answered {resp.status}: {str(message or 'no details')[:200]}")
    audio = ""
    for step in (data.get("steps") or []) if isinstance(data, dict) else []:
        if step.get("type") != "model_output":
            continue
        for part in step.get("content") or []:
            if part.get("type") == "audio" and part.get("data"):
                audio = part["data"]  # the last audio block wins, as in Google's example
    if not audio:
        raise RuntimeError("Gemini voice returned no audio.")
    return base64.b64decode(audio)
