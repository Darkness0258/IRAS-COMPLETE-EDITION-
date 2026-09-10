# IRAS 1.0 — Intelligent Responsive Autonomous System

IRAS is a local-first AI agent with a female voice/persona, tool use, persistent memory, desktop UI, local API, browser/file/system/Git capabilities, scheduling, and authenticated remote-node support.

It is deliberately **permissioned**: IRAS can operate your devices and accounts when you authorize them, but it does not bypass authentication or silently perform destructive actions.


## OpenRouter setup

OpenRouter is the default IRAS cloud brain. Copy `.env.example` to `.env`, then set:

```env
IRAS_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here
IRAS_MODEL=openrouter/free
```

The API key stays local in `.env` and `.env` is ignored by Git. Change `IRAS_MODEL` to any OpenRouter model ID you want to use.

## What is included

- Multi-step agent/tool loop
- Demo brain (works without API keys)
- OpenAI-compatible brain (OpenRouter and compatible endpoints)
- Ollama-compatible local brain
- Persistent SQLite conversation/fact memory
- Dynamic permission engine + per-action approvals
- JSONL audit log with secret redaction
- File read/write/copy/move/delete tools
- Arbitrary shell execution behind approval
- Windows/application/process/system tools
- Screenshot tool
- Public HTTP fetch with private-network SSRF protection
- OS browser opening
- Optional persistent Playwright browser session
- Git status/log/diff/commands with risk classification
- Authenticated public API calls using secret-by-name references (IRAS_SECRET_*)
- Agent-side remote-node invocation for authorized machines
- Natural Edge TTS with Windows speech fallback
- Optional local Whisper microphone transcription
- CLI
- Tkinter desktop chat UI
- FastAPI localhost service
- Authenticated IRAS remote node server
- Local recurring prompt scheduler
- Doctor/self-diagnostics
- Automated tests

## Install on Windows

```powershell
cd C:\workstation\Projects\IRAS
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
copy .env.example .env
iras --doctor
iras
```

For local microphone transcription:

```powershell
pip install -e ".[voice,dev]"
```

For full browser control:

```powershell
pip install -e ".[browser,dev]"
playwright install chromium
```

## Connect an actual AI brain

### OpenRouter / OpenAI-compatible
Edit `.env`:

```env
IRAS_PROVIDER=openai_compatible
IRAS_BASE_URL=https://openrouter.ai/api/v1
IRAS_API_KEY=YOUR_KEY
IRAS_MODEL=YOUR_TOOL_CAPABLE_MODEL_ID
```

### Ollama

```env
IRAS_PROVIDER=ollama
IRAS_BASE_URL=http://127.0.0.1:11434/v1
IRAS_MODEL=qwen2.5-coder:7b
IRAS_API_KEY=
```

Choose a model that supports tool/function calling for best results.

## Commands

```powershell
iras                 # interactive agent
iras --doctor        # diagnostics
iras --tools         # list capabilities
iras-desktop         # desktop UI
iras-api             # local HTTP API (127.0.0.1:8765)
iras-node             # authenticated remote node (127.0.0.1:8770)
iras-scheduler        # scheduled-prompt worker
```

## Permission levels

| Level | Meaning | Examples |
|---|---|---|
| 0 | READ | read file, system info, git status |
| 1 | SAFE_ACTION | open URL, create folder, launch normal app |
| 2 | SYSTEM_ACTION | arbitrary shell, write/move files, browser click |
| 3 | CRITICAL | destructive delete, force push, dangerous shell patterns |

By default levels 0–1 run automatically. Levels 2–3 require interactive approval. Critical actions are always confirmed.

## Voice

IRAS is voice-first. Spoken replies default to **on**. `edge-tts` provides the natural `en-US-AriaNeural` voice and MPV plays the generated audio. If Edge TTS or MPV fails on Windows, IRAS falls back to Windows SAPI and now reports the exact backend error instead of failing silently.

Useful commands:

```text
voice          # toggle spoken replies
voice on       # enable spoken replies
voice off      # disable spoken replies
voice test     # speak a test phrase and report the backend
listen         # record one microphone utterance and send it to IRAS
mic            # alias for listen
```

You can also test TTS before starting the chat:

```powershell
iras --voice-test
```

Microphone speech-to-text requires the voice extras:

```powershell
pip install -e ".[voice,dev]"
```

## API security

`iras-api` binds to localhost by default. If you expose it over a network, set a strong `IRAS_API_TOKEN` and put it behind TLS/authentication. API chat does not interactively approve elevated actions.

## Remote nodes

Run `iras-node` on a computer you own. A bearer token is mandatory for tool execution. Remote-node permissions default to Level 1, and critical actions remain blocked.

## Important boundary

IRAS is designed to access **systems, accounts, devices, APIs, and machines you own or are authorized to operate**. It is not an authentication-bypass or unauthorized-access framework.

## External authenticated APIs

Store service tokens in `.env` using names such as `IRAS_SECRET_GITHUB=...`. IRAS can reference the variable name with `api_request`; the raw token is injected inside the tool and is not passed through the model arguments. GET/HEAD are read-only; POST/PUT/PATCH require system approval; DELETE is critical.

## Calling remote IRAS nodes

Put the node token on the controlling machine in an `IRAS_SECRET_*` variable, then IRAS can use `remote_invoke` with the node URL and secret variable name. The remote node enforces its own independent permission cap as a second safety layer.

## Anime-inspired voice profiles (v1.2.0)

IRAS now has synchronized speech + personality profiles. The default is `anime_soft`.

Inside IRAS:

```text
voice styles
voice style soft
voice style genki
voice style cool
voice style normal
voice test
```

Profiles:
- `anime_soft` — en-US-JennyNeural, young-adult, warm, natural-pitch and gentle.
- `anime_genki` — en-US-JennyNeural, faster/brighter and energetic.
- `anime_cool` — en-US-AriaNeural, controlled and composed.
- `normal` — standard Aria voice/personality.

Set the startup profile in `.env`:

```env
IRAS_VOICE_PROFILE=anime_soft
```

These are original anime-inspired assistant profiles; they are not intended to imitate a specific character or actor.


## Personality / roleplay

IRAS v1.3.0 uses a young-adult, loving, concise personality by default.

- Replies are normally 1-3 sentences.
- Affection is subtle rather than repetitive.
- Playful jealousy is rare and non-controlling.
- Pranks are harmless and verbal only.
- Serious work automatically overrides roleplay.

See `ROLEPLAY_GUIDE.md` for the full behavior contract.


## Autonomous personality adaptation

IRAS v1.4.0 learns communication style by herself.

She gradually adapts warmth, affection, humor, teasing, brevity, formality, maturity and related style traits from conversation patterns. OpenRouter can also invoke an internal bounded `adapt_personality` tool when it detects meaningful evidence.

No personality sliders are required.

Use `personality status` only if you want to inspect the learned profile. `personality reset` restores defaults.

See `SELF_ADAPTING_PERSONALITY.md`.


## Human-like spoken output

IRAS v1.4.1 preprocesses assistant replies before TTS so she does not read emoji, Markdown syntax, raw URLs, decorative symbols, or code punctuation aloud. The original technical response remains unchanged on screen.

See `HUMAN_SPEECH.md`.


# IRAS Cloud v2.1

IRAS now includes:
- hosted FastAPI brain
- PostgreSQL-backed shared memory
- browser/PWA client
- native Android client source with mic + Android TTS
- Windows remote desktop client with IRAS voice
- Docker deployment for Koyeb
- GitHub Actions that build an installable debug APK and Windows EXE

See `CLOUD_DEPLOY.md`, `BUILD_APPS.md`, and `CLOUD_ARCHITECTURE.md`.


## Recommended cloud stack (v2.1)

```text
Backend  : Render Free
Database : Supabase Free PostgreSQL
AI       : OpenRouter
Web app  : served by Render
Android  : APK client
Windows  : EXE client
```

See `RENDER_SUPABASE_DEPLOY.md`.

Generate the client/server access token with:

```powershell
.\generate-iras-token.ps1
```
