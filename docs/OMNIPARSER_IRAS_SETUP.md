# OmniParser for IRAS v3.7

IRAS v3.7 uses Windows UI Automation first and OmniParser for visual-only
interfaces such as WebViews, Electron/custom-rendered controls, browser canvas
surfaces, and UI that exposes little useful accessibility information.

## Automatic start on demand

You no longer need to manually start OmniParser before every IRAS session.
When `device_computer_observe` needs vision, IRAS performs this bounded sequence:

```text
UI Automation
    -> foreground OmniParser grounding when UIA is insufficient
    -> desktop OmniParser grounding only when auto-scope foreground grounding
       produced no usable result
```

Before the first OmniParser parse request IRAS probes `/probe/`. If the endpoint
is already ready, IRAS reuses it. If the endpoint is local and unavailable,
IRAS can start a configured/discovered OmniParser process with `shell=False`,
wait for `/probe/`, and then continue the original observation.

IRAS **does not install OmniParser or download model weights automatically**.
The one-time OmniParser installation/weights setup is still explicit.

Default local endpoint when autostart is enabled:

```text
http://127.0.0.1:8010
```

The runtime log is written to:

```text
%USERPROFILE%\.iras\omniparser\omniparser.log
```

## Recommended one-time configuration

If your OmniParser checkout is in a standard project location such as
`D:\Projects\OmniParser`, IRAS attempts to discover it automatically. Otherwise
set the root once:

```powershell
[Environment]::SetEnvironmentVariable(
  "IRAS_OMNIPARSER_ROOT",
  "D:\Projects\OmniParser",
  "User"
)
```

The local endpoint may also be set explicitly:

```powershell
[Environment]::SetEnvironmentVariable(
  "IRAS_OMNIPARSER_URL",
  "http://127.0.0.1:8010",
  "User"
)
```

IRAS looks for an OmniParser virtual-environment Python under the root before
falling back to `python`/`python3` on PATH. On Windows, PaddleOCR 2.x and
PyTorch can conflict if Paddle loads its DLLs before torch. The built-in
autostart path therefore preloads `torch` in the child interpreter before
running the OmniParser server module. This is automatic and does not weaken
process isolation or use a shell.

For the current Microsoft OmniParser code path, use the legacy PaddleOCR API
that OmniParser calls directly:

```powershell
.\.venv\Scripts\python.exe -m pip install "paddleocr==2.10.0"
```

The default generated server command is conceptually equivalent to:

```text
python -c "import runpy, torch, uvicorn; ns=runpy.run_module('omniparserserver', run_name='iras_omniparser_runtime', alter_sys=False); a=ns['args']; uvicorn.run(ns['app'], host=a.host, port=a.port, reload=False)" \
  --caption_model_name florence2 \
  --caption_model_path ../../weights/icon_caption_florence \
  --device cpu \
  --BOX_TRESHOLD 0.05 \
  --host 127.0.0.1 \
  --port 8010
```

For a nonstandard OmniParser installation, define the exact argument vector as
JSON. It is executed directly with `shell=False`:

```powershell
[Environment]::SetEnvironmentVariable(
  "IRAS_OMNIPARSER_START_JSON",
  '["D:\\OmniParser\\.venv\\Scripts\\python.exe","-m","omniparserserver","--caption_model_name","florence2","--caption_model_path","../../weights/icon_caption_florence","--device","cpu","--BOX_TRESHOLD","0.05","--host","127.0.0.1","--port","8010"]',
  "User"
)
```

Useful settings:

```text
IRAS_OMNIPARSER_AUTOSTART=true
IRAS_OMNIPARSER_START_TIMEOUT=45
IRAS_OMNIPARSER_TIMEOUT=120
IRAS_OMNIPARSER_CACHE_TTL=180
IRAS_OMNIPARSER_PROBE_TIMEOUT=4
IRAS_OMNIPARSER_DEVICE=cpu
IRAS_OMNIPARSER_BOX_THRESHOLD=0.05
IRAS_COMPUTER_VISION_MAX_WIDTH=1600
IRAS_COMPUTER_VISION_MAX_HEIGHT=1200
IRAS_COMPUTER_OBSERVATION_TTL=30
IRAS_VISUAL_ACTION_MIN_CONFIDENCE=0.72
```

To disable process autostart while keeping support for an already-running
server:

```powershell
[Environment]::SetEnvironmentVariable(
  "IRAS_OMNIPARSER_AUTOSTART",
  "false",
  "User"
)
```

## CLI diagnostics

Inside the IRAS CLI:

```text
vision status
vision start
```

`vision start` performs the same bounded local startup path used automatically
when visual grounding is first required. Runtime ownership metadata is persisted
locally so `vision status` can report the IRAS-owned PID even after a new CLI
instance attaches to the already-running service.

## Safety behavior

OmniParser output is evidence, not permission. v3.7 converts UIA and vision
results into a unified scene graph with stable element IDs, confidence, and
provenance. Mouse actions still require a fresh observed element ID. Low-
confidence or ambiguous visual targets fail closed, raw model coordinates are
not accepted, and one state-changing input consumes its observation binding so
it cannot be replayed.

## R4 IRAS bridge and ROI acceleration

When IRAS starts a discovered local OmniParser installation, the default R4
launcher uses `src/iras/vision/omniparser_bridge_server.py` with OmniParser's own
Python environment. The bridge still provides `/probe/` and `/parse/`, but also
adds `/parse_text/` for lightweight EasyOCR-only text grounding. Full
Florence/YOLO models are initialized lazily on the first full parse instead of at
server startup.

This behavior is controlled by:

```text
IRAS_OMNIPARSER_BRIDGE=true
IRAS_OMNIPARSER_ROI_MAX_WIDTH=960
IRAS_OMNIPARSER_ROI_MAX_HEIGHT=720
IRAS_WHATSAPP_ROI_FASTPATH=true
```

Set `IRAS_OMNIPARSER_BRIDGE=false` only to force the older upstream-server
bootstrap. If a manually started upstream server is already listening, IRAS
reuses it; ROI text requests automatically fall back to `/parse/` if
`/parse_text/` is not supported.
