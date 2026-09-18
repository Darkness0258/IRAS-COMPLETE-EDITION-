param(
    [switch]$Repair,
    [switch]$SkipWeights,
    [switch]$SkipFullWarmup
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Get-Python312 {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:ProgramFiles\Python312\python.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $resolved = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1).Trim()
            if ($resolved -and (Test-Path $resolved)) { return $resolved }
        } catch {}
    }
    return $null
}

function Set-DotEnvValue([string]$Name, [string]$Value) {
    $path = Join-Path $PSScriptRoot ".env"
    if (-not (Test-Path $path)) {
        Copy-Item (Join-Path $PSScriptRoot ".env.example") $path
    }
    $content = Get-Content $path -Raw
    $escaped = [regex]::Escape($Name)
    if ($content -match "(?m)^$escaped=") {
        $content = [regex]::Replace($content, "(?m)^$escaped=.*$", "$Name=$Value")
    } else {
        $content = $content.TrimEnd() + "`r`n$Name=$Value`r`n"
    }
    Set-Content -Path $path -Value $content -Encoding UTF8
}


function Test-LocalPortAvailable([int]$Port) {
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new(
            [System.Net.IPAddress]::Loopback,
            $Port
        )
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) {
            try { $listener.Stop() } catch {}
        }
    }
}

function Get-ManagedOmniParserRoot([string]$RequestedRoot) {
    $requested = [IO.Path]::GetFullPath($RequestedRoot)
    if (-not (Test-Path $requested)) { return $requested }
    if (Test-Path (Join-Path $requested ".git")) { return $requested }

    $items = Get-ChildItem $requested -Force -ErrorAction SilentlyContinue
    if (-not $items) { return $requested }

    # Never delete or overwrite an existing unmanaged/legacy OmniParser tree.
    # A legacy service may still be using it. Create a separate checkout that
    # IRAS can own, update and stop/restart safely.
    $parent = Split-Path $requested -Parent
    $base = (Split-Path $requested -Leaf) + "-iras-managed"
    $candidate = Join-Path $parent $base
    $index = 2
    while ((Test-Path $candidate) -and -not (Test-Path (Join-Path $candidate ".git"))) {
        $candidate = Join-Path $parent ("$base-$index")
        $index += 1
    }
    Write-Warning "Preserving unmanaged OmniParser tree at $requested"
    Write-Host "IRAS will use a separate managed checkout at $candidate" -ForegroundColor Yellow
    return [IO.Path]::GetFullPath($candidate)
}

function Get-ManagedVisionPort {
    foreach ($port in 8010..8020) {
        if (Test-LocalPortAvailable $port) { return $port }
    }
    throw "No free local port was available for the IRAS-managed OmniParser bridge (8010-8020)."
}

if ($env:OS -ne "Windows_NT") {
    throw "The managed OmniParser bootstrap currently targets Windows."
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is required for OmniParser setup. Install Git and rerun this script."
}

$requestedRoot = if ($env:IRAS_OMNIPARSER_ROOT) {
    [Environment]::ExpandEnvironmentVariables($env:IRAS_OMNIPARSER_ROOT)
} else {
    Join-Path $HOME ".iras\OmniParser"
}
$root = Get-ManagedOmniParserRoot $requestedRoot
$parent = Split-Path $root -Parent
New-Item -ItemType Directory -Force -Path $parent | Out-Null

# If a previous IRAS-managed bridge is running, stop only that owned process
# before selecting a port. The runtime manager refuses to stop external/legacy
# OmniParser services, so an unrelated service is never killed here.
if ((Test-Path ".\.venv\Scripts\iras.exe") -and (Test-Path ".env")) {
    try {
        & .\.venv\Scripts\iras.exe --vision-stop *> $null
    } catch {}
}

$managedPort = Get-ManagedVisionPort
$managedUrl = "http://127.0.0.1:$managedPort"
Write-Host "Managed OmniParser endpoint: $managedUrl" -ForegroundColor DarkGray

$python312 = Get-Python312
if (-not $python312) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Python 3.12 is required by Microsoft OmniParser. Install Python 3.12 or winget, then rerun setup-omniparser.ps1."
    }
    Write-Host "Installing Python 3.12 for the isolated OmniParser runtime..." -ForegroundColor Cyan
    & winget install --id Python.Python.3.12 -e --scope user --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 installation failed with exit code $LASTEXITCODE." }
    $python312 = Get-Python312
    if (-not $python312) { throw "Python 3.12 installed but could not be located. Open a new PowerShell window and rerun setup-omniparser.ps1." }
}

if (-not (Test-Path (Join-Path $root ".git"))) {
    if (Test-Path $root) {
        $items = Get-ChildItem $root -Force -ErrorAction SilentlyContinue
        if ($items) { throw "Selected managed OmniParser target is unexpectedly non-empty: $root" }
    }
    Write-Host "Cloning Microsoft OmniParser into $root ..." -ForegroundColor Cyan
    & git clone --depth 1 https://github.com/microsoft/OmniParser.git $root
    if ($LASTEXITCODE -ne 0) { throw "OmniParser clone failed." }
} elseif ($Repair) {
    Write-Host "Refreshing the managed OmniParser checkout..." -ForegroundColor Cyan
    & git -C $root fetch origin master --depth 1
    if ($LASTEXITCODE -ne 0) { throw "OmniParser refresh failed." }
    & git -C $root checkout master
    & git -C $root pull --ff-only origin master
    if ($LASTEXITCODE -ne 0) { throw "OmniParser fast-forward update failed; local changes were left untouched." }
}

$omniPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $omniPython)) {
    Write-Host "Creating isolated OmniParser Python 3.12 environment..." -ForegroundColor Cyan
    & $python312 -m venv (Join-Path $root ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Could not create OmniParser virtual environment." }
}

Write-Host "Installing/repairing OmniParser dependencies..." -ForegroundColor Cyan
& $omniPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "OmniParser pip bootstrap failed." }
$filteredRequirements = Join-Path $env:TEMP "iras_omniparser_requirements.txt"
try {
    # IRAS uses OmniParser as a headless local vision engine. Skip upstream
    # demo/cloud/dev packages that are not imported by util.omniparser and can
    # force incompatible Hugging Face dependency ranges (for example Gradio).
    $excluded = '^\s*(paddle(paddle|ocr)|gradio|streamlit|azure-identity|anthropic|boto3|google-auth|dashscope|groq|pre-commit|pytest|pytest-asyncio|ruff|pyautogui|screeninfo|uiautomation)(?:\[[^\]]+\])?\s*([<>=!~].*)?$'
    Get-Content (Join-Path $root "requirements.txt") |
        Where-Object { $_ -notmatch $excluded } |
        Set-Content -Path $filteredRequirements -Encoding UTF8
    & $omniPython -m pip install -r $filteredRequirements
    if ($LASTEXITCODE -ne 0) { throw "OmniParser requirements installation failed." }
} finally {
    Remove-Item $filteredRequirements -Force -ErrorAction SilentlyContinue
}
# Remove stale top-level demo/dev packages left by an older managed install so
# pip does not report false dependency conflicts against the headless runtime.
# Windows PowerShell 5.1 promotes some native stderr warnings (for example
# "Skipping gradio as it is not installed") to NativeCommandError when the
# script-wide ErrorActionPreference is Stop.  This cleanup is optional, so run
# it with native stderr suppressed and decide only from the process exit code.
$cleanupPackages = @(
    "gradio", "gradio-client", "streamlit", "azure-identity",
    "anthropic", "boto3", "google-auth", "dashscope", "groq",
    "pre-commit", "pytest", "pytest-asyncio", "ruff", "pyautogui",
    "screeninfo", "uiautomation"
)
$previousErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = "SilentlyContinue"
    & $omniPython -m pip uninstall -y @cleanupPackages 1>$null 2>$null
    $cleanupExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousErrorActionPreference
}
if ($cleanupExitCode -ne 0) {
    Write-Warning "Optional OmniParser demo/dev package cleanup returned exit code $cleanupExitCode; continuing with the headless runtime."
}

# Current upstream has historically had compatibility drift around these APIs.
# Keep the IRAS-managed environment on the interfaces used by upstream master.
& $omniPython -m pip install "numpy==1.26.4" "transformers==4.49.0" "huggingface-hub==0.36.2" "pydantic==2.10.6" "fastapi>=0.115" "uvicorn>=0.30" "openai==1.3.5"
if ($LASTEXITCODE -ne 0) { throw "OmniParser compatibility/runtime dependencies failed." }

if (-not $SkipWeights) {
    Write-Host "Provisioning OmniParser V2 detector and Florence caption weights..." -ForegroundColor Cyan
    $weightScript = Join-Path $env:TEMP "iras_omniparser_weights.py"
    @'
from pathlib import Path
import shutil
from huggingface_hub import hf_hub_download, snapshot_download
import os

root = Path(os.environ["IRAS_OMNI_SETUP_ROOT"]).resolve()
weights = root / "weights"
weights.mkdir(parents=True, exist_ok=True)

detector = weights / "icon_detect_v3" / "model.pt"
if not detector.is_file():
    hf_hub_download(
        repo_id="microsoft/OmniParser-v2.0",
        filename="icon_detect_v3/model.pt",
        revision="refs/pr/37",
        local_dir=str(weights),
    )
else:
    print("Reusing existing detector weight:", detector)

# Never delete/replace a live Florence directory during -Repair.  A running
# managed bridge may memory-map model.safetensors on Windows, which makes
# shutil.rmtree fail with WinError 5.  Populate only missing files in-place.
dst = weights / "icon_caption_florence"
dst.mkdir(parents=True, exist_ok=True)
for filename in (
    "icon_caption/config.json",
    "icon_caption/generation_config.json",
    "icon_caption/model.safetensors",
):
    target = dst / Path(filename).name
    if target.is_file() and target.stat().st_size > 0:
        print("Reusing existing Florence asset:", target)
        continue
    downloaded = Path(hf_hub_download(
        repo_id="microsoft/OmniParser-v2.0",
        filename=filename,
        local_dir=str(weights),
    ))
    if downloaded.resolve() != target.resolve():
        shutil.copy2(downloaded, target)

if not detector.is_file():
    raise SystemExit("missing icon_detect_v3/model.pt")
if not (dst / "model.safetensors").is_file():
    raise SystemExit("missing icon_caption_florence/model.safetensors")
snapshot_download(
    repo_id="microsoft/Florence-2-base",
    allow_patterns=["*.json", "*.py", "*.txt", "*.model", "*.tiktoken", "*.vocab", "*.merges"],
)
# The fine-tuned icon-caption config currently points its trust_remote_code
# auto_map at microsoft/Florence-2-base-ft. Cache that implementation during
# setup too so the first full parse does not depend on a surprise network fetch.
snapshot_download(
    repo_id="microsoft/Florence-2-base-ft",
    allow_patterns=["*.py", "*.json"],
)
print("OmniParser weights ready:", weights)
'@ | Set-Content -Path $weightScript -Encoding UTF8
    $env:IRAS_OMNI_SETUP_ROOT = $root
    try {
        & $omniPython $weightScript
        if ($LASTEXITCODE -ne 0) { throw "OmniParser model-weight provisioning failed." }
    } finally {
        Remove-Item $weightScript -Force -ErrorAction SilentlyContinue
        Remove-Item Env:\IRAS_OMNI_SETUP_ROOT -ErrorAction SilentlyContinue
    }
}

Set-DotEnvValue "IRAS_OMNIPARSER_ROOT" $root
Set-DotEnvValue "IRAS_OMNIPARSER_AUTOSTART" "true"
Set-DotEnvValue "IRAS_OMNIPARSER_ALLOW_EXTERNAL" "false"
Set-DotEnvValue "IRAS_OMNIPARSER_EAGER_START" "true"
Set-DotEnvValue "IRAS_OMNIPARSER_WATCHDOG" "true"
Set-DotEnvValue "IRAS_OMNIPARSER_WATCHDOG_SECONDS" "20"
Set-DotEnvValue "IRAS_OMNIPARSER_URL" $managedUrl
Set-DotEnvValue "IRAS_OMNIPARSER_BRIDGE" "true"
Set-DotEnvValue "IRAS_OMNIPARSER_DISABLE_PADDLE" "true"
Set-DotEnvValue "IRAS_OMNIPARSER_DEVICE" "cpu"
Set-DotEnvValue "IRAS_OMNIPARSER_TEXT_PREWARM" "true"

$env:IRAS_OMNIPARSER_ROOT = $root
$env:IRAS_OMNIPARSER_AUTOSTART = "true"
$env:IRAS_OMNIPARSER_ALLOW_EXTERNAL = "false"
$env:IRAS_OMNIPARSER_EAGER_START = "true"
$env:IRAS_OMNIPARSER_WATCHDOG = "true"
$env:IRAS_OMNIPARSER_URL = $managedUrl
$env:IRAS_OMNIPARSER_DISABLE_PADDLE = "true"
$env:IRAS_OMNIPARSER_DEVICE = "cpu"

Write-Host "OmniParser managed runtime is provisioned at $root" -ForegroundColor Green
if (Test-Path ".\.venv\Scripts\iras.exe") {
    Write-Host "Starting and probing the IRAS-managed OmniParser bridge..." -ForegroundColor Cyan
    & .\.venv\Scripts\iras.exe --vision-start
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Provisioning completed, but OmniParser did not start. Check $HOME\.iras\omniparser\omniparser.log"
        exit 2
    }

    Write-Host "Waiting for EasyOCR background warmup..." -ForegroundColor Cyan
    $probeScript = Join-Path $env:TEMP "iras_omniparser_probe.py"
    @'
import os
import time
import httpx

base = os.environ.get("IRAS_OMNI_PROBE_URL", "http://127.0.0.1:8010").rstrip("/")
deadline = time.monotonic() + 240
last = {}
while time.monotonic() < deadline:
    try:
        response = httpx.get(base + "/probe/", timeout=3)
        response.raise_for_status()
        last = response.json()
        state = str(last.get("text_model_state") or "")
        if state == "ready":
            print("EasyOCR warmup ready", last.get("text_model_warmup_ms"))
            raise SystemExit(0)
        if state == "failed":
            print("EasyOCR warmup failed:", last.get("text_model_error"))
            raise SystemExit(2)
    except SystemExit:
        raise
    except Exception as exc:
        last = {"error": f"{type(exc).__name__}: {exc}"}
    time.sleep(1)
print("EasyOCR warmup timeout:", last)
raise SystemExit(2)
'@ | Set-Content -Path $probeScript -Encoding UTF8
    $env:IRAS_OMNI_PROBE_URL = $managedUrl
    try {
        & .\.venv\Scripts\python.exe $probeScript
        if ($LASTEXITCODE -ne 0) { throw "OmniParser EasyOCR warmup failed. Check the OmniParser log." }
    } finally {
        Remove-Item $probeScript -Force -ErrorAction SilentlyContinue
        Remove-Item Env:\IRAS_OMNI_PROBE_URL -ErrorAction SilentlyContinue
    }

    if (-not $SkipFullWarmup) {
        Write-Host "Loading and smoke-testing full Florence/YOLO visual semantics once..." -ForegroundColor Cyan
        $fullWarmup = Join-Path $env:TEMP "iras_omniparser_full_warmup.py"
        @'
import base64
import io
import os
import httpx
from PIL import Image, ImageDraw

base = os.environ.get("IRAS_OMNI_PROBE_URL", "http://127.0.0.1:8010").rstrip("/")
image = Image.new("RGB", (320, 180), "white")
draw = ImageDraw.Draw(image)
draw.rectangle((40, 50, 160, 105), outline="black", width=3)
draw.text((65, 70), "IRAS", fill="black")
buffer = io.BytesIO()
image.save(buffer, format="PNG")
payload = base64.b64encode(buffer.getvalue()).decode("ascii")
response = httpx.post(
    base + "/parse/",
    json={"base64_image": payload},
    timeout=600,
)
if response.status_code >= 400:
    print("Full OmniParser HTTP failure:", response.status_code, response.text[:4000])
response.raise_for_status()
data = response.json()
if not isinstance(data.get("parsed_content_list"), list):
    raise SystemExit("full OmniParser parse returned an invalid payload")
print("Full OmniParser warmup ready; elements:", len(data.get("parsed_content_list") or []))
'@ | Set-Content -Path $fullWarmup -Encoding UTF8
        $env:IRAS_OMNI_PROBE_URL = $managedUrl
        try {
            & .\.venv\Scripts\python.exe $fullWarmup
            if ($LASTEXITCODE -ne 0) { throw "Full OmniParser warmup/smoke test failed. Check the OmniParser log." }
        } finally {
            Remove-Item $fullWarmup -Force -ErrorAction SilentlyContinue
            Remove-Item Env:\IRAS_OMNI_PROBE_URL -ErrorAction SilentlyContinue
        }
    }
}
