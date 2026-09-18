# OmniParser for IRAS v5.0 RC3

IRAS uses Windows UI Automation first and Microsoft OmniParser as the visual grounding layer for WebViews, Electron/custom-rendered controls, browser canvas surfaces, and interfaces that expose insufficient accessibility semantics.

## Managed by IRAS by default

OmniParser is now a first-class IRAS runtime service. On Windows, `install.ps1` provisions the managed runtime under:

```text
%USERPROFILE%\.iras\OmniParser
```

The setup creates an isolated Python 3.12 environment, installs the Microsoft OmniParser dependencies used by the IRAS bridge, downloads the current V2 detector/caption weights, and writes the resulting root into `.env`.
It also caches the Florence processor/code assets, waits for EasyOCR warmup, and performs one local full-parser smoke test so the first real visual task does not discover a missing model/dependency late.

Normal startup:

```powershell
.\run-iras.ps1
```

The launcher performs a bounded `--vision-start` before interactive IRAS begins. If the managed environment or weights are missing, it runs `setup-omniparser.ps1` once and retries. Direct `iras` startup also launches an in-process OmniParser supervisor, so the service remains self-healing even when the PowerShell launcher is bypassed.

The default visual route is:

```text
Windows UI Automation
    -> accessibility/semantic grounding
    -> EasyOCR ROI/text grounding
    -> full OmniParser Florence/YOLO semantics when necessary
    -> fresh semantic verification before state-changing input
```

OmniParser evidence never grants permission by itself. Existing ToolRegistry approval levels, Remote authorization, bridge roots, fresh-observation requirements, confidence thresholds, and the emergency stop remain authoritative.

## Current Microsoft V2 layout

IRAS provisions the detector and caption assets expected by current Microsoft OmniParser master:

```text
weights\icon_detect_v3\model.pt
weights\icon_caption_florence\config.json
weights\icon_caption_florence\generation_config.json
weights\icon_caption_florence\model.safetensors
```

The detector is obtained from the Microsoft V2 model revision currently referenced by the upstream README. The caption files are downloaded from `microsoft/OmniParser-v2.0`.

## Windows stability hardening

Current upstream `util.utils` imports/constructs PaddleOCR at module import time, while current `Omniparser.parse` explicitly uses EasyOCR. That eager Paddle initialization can create avoidable native-library conflicts with PyTorch on Windows. The IRAS bridge therefore uses a fail-closed Paddle stub by default and runs EasyOCR for OCR grounding:

```text
IRAS_OMNIPARSER_DISABLE_PADDLE=true
```

If upstream ever attempts to invoke the stub, it raises instead of silently changing OCR behavior. Set the flag to `false` only when you intentionally maintain a compatible Paddle installation yourself.

## Runtime lifecycle

Defaults:

```text
IRAS_OMNIPARSER_AUTOSTART=true
IRAS_OMNIPARSER_EAGER_START=true
IRAS_OMNIPARSER_WATCHDOG=true
IRAS_OMNIPARSER_WATCHDOG_SECONDS=20
IRAS_OMNIPARSER_URL=http://127.0.0.1:8010
IRAS_OMNIPARSER_BRIDGE=true
IRAS_OMNIPARSER_DISABLE_PADDLE=true
IRAS_OMNIPARSER_TEXT_PREWARM=true
```

The IRAS bridge binds to loopback. When IRAS creates the bridge it generates a random per-process control token, stores it in the local runtime state, and uses it for authenticated stop/restart. IRAS will never process-manage a remote OmniParser URL.

Commands:

```powershell
iras --vision-status
iras --vision-start
iras --vision-restart
iras --vision-stop
```

Interactive equivalents:

```text
vision status
vision start
vision restart
vision stop
```

Model-facing runtime tools are also registered so IRAS can inspect, start, and self-heal its own vision subsystem. Restart/stop remain SYSTEM_ACTION operations through the normal permission engine.

## Logs and state

```text
%USERPROFILE%\.iras\omniparser\omniparser.log
%USERPROFILE%\.iras\omniparser\runtime.json
```

`iras --doctor` reports three separate checks: installation completeness, configuration/management mode, and live service readiness.

## Full-model loading

The local HTTP bridge starts eagerly, and EasyOCR can warm in the background. Florence/YOLO stays lazy until the first full visual parse. This avoids loading the heavy model into memory when UIA or text grounding already resolves the interface.

## Manual repair

To repair/update only the managed OmniParser environment:

```powershell
.\setup-omniparser.ps1 -Repair
```

To reprovision dependencies without re-downloading weights:

```powershell
.\setup-omniparser.ps1 -Repair -SkipWeights
```

For a constrained repair where you intentionally want to defer the one-time full Florence/YOLO smoke test:

```powershell
.\setup-omniparser.ps1 -Repair -SkipFullWarmup
```

## Opt-out / external server

To disable all local process autostart:

```powershell
[Environment]::SetEnvironmentVariable("IRAS_OMNIPARSER_AUTOSTART", "false", "User")
```

IRAS can still consume a manually managed endpoint through `IRAS_OMNIPARSER_URL`. External/remote services are probed but never killed or restarted by IRAS.
