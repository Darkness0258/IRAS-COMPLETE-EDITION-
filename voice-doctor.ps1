param(
    [string]$ProjectRoot = "D:\Projects\IRAS-complete",
    [string]$Server = "https://iras-cloud.onrender.com",
    [switch]$TestMicrophone,
    [switch]$PlayRenderAudio
)

$ErrorActionPreference = "Continue"
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "IRAS virtual environment Python was not found: $Python"
}

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host "=== $Title ===" -ForegroundColor Cyan
}

function Read-DotEnvValue([string]$Name) {
    $envPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $envPath)) {
        return ""
    }

    foreach ($line in Get-Content $envPath) {
        if ($line -match "^\s*$([regex]::Escape($Name))\s*=\s*(.*?)\s*$") {
            $value = $Matches[1].Trim()
            if (
                ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))
            ) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            return $value
        }
    }

    return ""
}

Write-Host "IRAS RC12 Voice Doctor" -ForegroundColor Green
Write-Host "Project: $ProjectRoot"
Write-Host "Server : $Server"

Write-Section "1. Runtime identity"

& $Python -c "import sys, iras; from iras.remote_protocol import REMOTE_PROTOCOL_VERSION; print('Python:', sys.executable); print('IRAS:', iras.__version__); print('Remote Protocol:', REMOTE_PROTOCOL_VERSION)"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Runtime identity FAILED." -ForegroundColor Red
}

Write-Section "2. Voice packages"

$packageProbe = @'
import importlib
mods = ["edge_tts", "sounddevice", "soundfile", "faster_whisper"]
for name in mods:
    try:
        module = importlib.import_module(name)
        version = getattr(module, "__version__", "installed")
        print(f"{name}: OK ({version})")
    except Exception as exc:
        print(f"{name}: FAIL ({type(exc).__name__}: {exc})")
'@

$packageProbe | & $Python -

Write-Section "3. Microphone inventory"

$micInventory = @'
from iras.voice.stt import Listener

status = Listener.microphone_status()
print("Available:", status.get("available"))
print("Input devices:", status.get("count"))
print("Selected:", status.get("selected"))

for dev in status.get("devices", []):
    index = dev.get("index")
    name = dev.get("name")
    channels = dev.get("channels")
    rate = int(float(dev.get("default_samplerate") or 0))
    print(f"  [{index}] {name} | {channels} ch | {rate} Hz")
'@

$micInventory | & $Python -

if ($TestMicrophone) {
    Write-Section "4. Live microphone + Whisper test"

    Write-Host "Speak a short sentence when Listening appears." -ForegroundColor Yellow

    $micTest = @'
from iras.config import Settings
from iras.voice.stt import Listener

settings = Settings.load()
listener = Listener(settings.whisper_model, settings.listen_seconds)

print(
    f"Listening for about {settings.listen_seconds} seconds "
    f"using Whisper model '{settings.whisper_model}'..."
)

heard = listener.listen_once()

if heard:
    print("MIC/STT PASS")
    print("Heard:", heard)
else:
    print("MIC/STT WARNING: no speech was transcribed.")
'@

    $micTest | & $Python -

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Microphone/STT test FAILED." -ForegroundColor Red
    }
}
else {
    Write-Host "Live recording skipped. Add -TestMicrophone to test microphone + Whisper." -ForegroundColor DarkGray
}

Write-Section "5. Windows native TTS"

& $Python -m iras.cli --voice-test windows
if ($LASTEXITCODE -eq 0) {
    Write-Host "Windows SAPI command PASS." -ForegroundColor Green
} else {
    Write-Host "Windows SAPI command FAILED." -ForegroundColor Red
}

Write-Section "6. Edge TTS + MPV"

& $Python -m iras.cli --voice-test edge
if ($LASTEXITCODE -eq 0) {
    Write-Host "Edge TTS + MPV command PASS." -ForegroundColor Green
} else {
    Write-Host "Edge TTS + MPV command FAILED." -ForegroundColor Red
}

Write-Section "7. MPV discovery"

$mpv = Get-Command mpv -ErrorAction SilentlyContinue

if (-not $mpv) {
    $candidates = @(
        "C:\Program Files\MPV Player\mpv.exe",
        "C:\Program Files\mpv\mpv.exe",
        "$env:LOCALAPPDATA\Programs\mpv\mpv.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $mpv = Get-Item $candidate
            break
        }
    }
}

if ($mpv) {
    $mpvPath = if ($mpv.Source) { $mpv.Source } else { $mpv.FullName }
    Write-Host "MPV: $mpvPath" -ForegroundColor Green
} else {
    Write-Host "MPV: NOT FOUND" -ForegroundColor Red
}

Write-Section "8. Render authentication"

$token = $env:IRAS_CLOUD_TOKEN
if (-not $token) {
    $token = $env:IRAS_API_TOKEN
}
if (-not $token) {
    $token = Read-DotEnvValue "IRAS_CLOUD_TOKEN"
}
if (-not $token) {
    $token = Read-DotEnvValue "IRAS_API_TOKEN"
}

if (-not $token) {
    Write-Host "No IRAS_CLOUD_TOKEN or IRAS_API_TOKEN found." -ForegroundColor Yellow
    Write-Host "Render authenticated voice checks are skipped."
    Write-Host ""
    Write-Host "Create/configure .env first, then rerun this script."
    exit 0
}

$headers = @{
    Authorization = "Bearer $token"
}

Write-Host "Cloud token located. Value is intentionally not displayed." -ForegroundColor Green

Write-Section "9. Render voice health"

try {
    $health = Invoke-RestMethod `
        -Method Get `
        -Uri "$Server/v1/voice/health" `
        -Headers $headers `
        -TimeoutSec 30

    $health | ConvertTo-Json -Depth 10
    Write-Host "Render voice-health PASS." -ForegroundColor Green
}
catch {
    $statusCode = $null

    try {
        $statusCode = [int]$_.Exception.Response.StatusCode
    }
    catch {}

    if ($statusCode -eq 404) {
        Write-Host "Render /v1/voice/health returned 404." -ForegroundColor Yellow
        Write-Host "This normally means the fixed RC12 source has not been deployed to Render yet."
    }
    else {
        Write-Host "Render voice-health FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Section "10. Render TTS generation"

$tmp = Join-Path $env:TEMP "iras-render-voice-test.mp3"

try {
    if (Test-Path $tmp) {
        Remove-Item $tmp -Force
    }

    $body = @{
        text = "IRAS voice test online."
        language = "en-US"
        voice_gender = "female"
        mood = "calm"
    } | ConvertTo-Json

    $response = Invoke-WebRequest `
        -Method Post `
        -Uri "$Server/v1/tts" `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $body `
        -OutFile $tmp `
        -PassThru `
        -TimeoutSec 90

    $item = Get-Item $tmp

    if ($item.Length -lt 256) {
        throw "Render returned an unexpectedly small audio file ($($item.Length) bytes)."
    }

    Write-Host "Render TTS PASS: $($item.Length) bytes" -ForegroundColor Green
    Write-Host "File: $tmp"

    if ($response.Headers["X-IRAS-Voice"]) {
        Write-Host "Voice: $($response.Headers['X-IRAS-Voice'])"
    }

    if ($PlayRenderAudio) {
        if ($mpv) {
            $mpvPath = if ($mpv.Source) { $mpv.Source } else { $mpv.FullName }

            Write-Host "Playing Render TTS audio..." -ForegroundColor Cyan
            & $mpvPath `
                --no-config `
                --no-video `
                --audio-device=auto `
                --volume=100 `
                $tmp

            if ($LASTEXITCODE -eq 0) {
                Write-Host "Render audio playback command PASS." -ForegroundColor Green
            }
            else {
                Write-Host "MPV returned exit code $LASTEXITCODE." -ForegroundColor Red
            }
        }
        else {
            Write-Host "Cannot play Render audio because MPV was not found." -ForegroundColor Yellow
        }
    }
}
catch {
    Write-Host "Render TTS FAILED: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Section "11. Summary"

Write-Host "Voice doctor completed."
Write-Host "If local SAPI + Edge tests are audible and Render TTS produced audio, PC output is healthy."
Write-Host "If -TestMicrophone transcribed you correctly, PC microphone/STT is healthy."
Write-Host "A 404 only for /v1/voice/health means the new fixed code still needs to be pushed/deployed."
