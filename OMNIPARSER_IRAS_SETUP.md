# Optional OmniParser V2 setup for IRAS v3.5

IRAS v3.5 works immediately with Windows UI Automation. OmniParser is an
optional visual grounding backend for custom-rendered interfaces such as
Electron/canvas-style UIs where UIA exposes few or no useful controls.

IRAS talks to the official OmniParser FastAPI server. The expected contract is:

- `GET /probe/`
- `POST /parse/` with JSON `{ "base64_image": "..." }`
- response containing `parsed_content_list` and optionally
  `som_image_base64` / `latency`

## IRAS configuration

After you have an OmniParser server running, set the endpoint for the Windows
IRAS process:

```powershell
[Environment]::SetEnvironmentVariable(
  "IRAS_OMNIPARSER_URL",
  "http://127.0.0.1:8010",
  "User"
)
```

If the endpoint uses bearer authentication:

```powershell
[Environment]::SetEnvironmentVariable(
  "IRAS_OMNIPARSER_API_KEY",
  "YOUR_KEY",
  "User"
)
```

Restart IRAS.exe after changing environment variables.

Useful optional settings:

```text
IRAS_OMNIPARSER_TIMEOUT=120
IRAS_OMNIPARSER_PROBE_TIMEOUT=4
IRAS_COMPUTER_VISION_MAX_WIDTH=1600
IRAS_COMPUTER_VISION_MAX_HEIGHT=1200
IRAS_COMPUTER_OBSERVATION_TTL=30
```

## Official backend

Use the Microsoft OmniParser repository and its V2 weights. The official
OmniTool includes an `omniparserserver` FastAPI component. A typical server
command from the project is equivalent to:

```text
python -m omniparserserver \
  --caption_model_name florence2 \
  --caption_model_path ../../weights/icon_caption_florence \
  --device cpu \
  --BOX_TRESHOLD 0.05 \
  --host 127.0.0.1 \
  --port 8010
```

Use a separate Python 3.12 environment for OmniParser rather than modifying the
IRAS runtime. GPU is faster, but the Microsoft project documents CPU execution
as supported. On older/low-VRAM GPUs, CPU mode is the safer starting point.

IRAS does not auto-download model weights or silently install OmniParser. This
keeps the desktop client small and keeps screenshot transmission opt-in.
