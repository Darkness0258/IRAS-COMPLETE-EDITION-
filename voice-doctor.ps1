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
print("Configured:", status.get("configured"))
print("Auto-selected:", status.get("selected"), "-", status.get("selected_name"))
print()
print("Ranked input devices (highest reliability first):")
for dev in sorted(status.get("devices", []), key=lambda x: x.get("score", 0), reverse=True):
    index = dev.get("index")
    name = dev.get("name")
    channels = dev.get("channels")
    rate = int(float(dev.get("default_samplerate") or 0))
    host = dev.get("hostapi") or "unknown host API"
    marker = " <AUTO>" if index == status.get("selected") else ""
    default = " <WINDOWS DEFAULT>" if dev.get("is_default") else ""
    print(f"  [{index}] score={dev.get('score', 0):>4} | {host} | {name} | {channels} ch | {rate} Hz{marker}{default}")
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

print("LEVEL TEST: speak normally for the next 2 seconds...")
level = Listener.test_input_level(seconds=2.0)
print(
    "LEVEL:",
    f"device={level['device']} ({level['name']})",
    f"rate={level['sample_rate']}Hz",
    f"signal={level['signal']}",
    f"rms={level['rms']:.5f}",
    f"peak={level['peak']:.5f}",
    f"dBFS={level['dbfs']:.1f}",
)
if level["signal"] in {"silent", "very-low"}:
    print("MIC LEVEL WARNING: input is very quiet. Check Windows input volume/privacy or try IRAS_MIC_DEVICE=<index>.")

print()
print(
    f"WHISPER TEST: say a short English, Roman Urdu, or Urdu sentence "
    f"using model '{settings.whisper_model}'..."
)
heard = listener.listen_once()

if heard:
    print("MIC/STT PASS")
    print("Heard:", heard)
    print(
        "Capture:",
        f"device={listener.last_device} ({listener.last_device_name})",
        f"rate={listener.last_sample_rate}Hz",
        f"rms={listener.last_rms:.5f}",
        f"peak={listener.last_peak:.5f}",
        f"noise={listener.last_noise_floor:.5f}",
        f"threshold={listener.last_energy_threshold:.5f}",
        f"clipping={listener.last_clipping_ratio * 100:.2f}%",
        f"stt_attempts={listener.last_transcription_attempts}",
    )
    if listener.last_clipping_ratio >= 0.01:
        print("MIC LEVEL WARNING: capture is clipping. Lower Windows microphone input level/boost if recognition remains inaccurate.")
    print(
        "Whisper language:",
        listener.last_language or "unknown",
        f"confidence={listener.last_language_probability:.3f}",
    )
else:
    print("MIC/STT WARNING: audio opened but no speech was transcribed.")
    print(
        "Capture:",
        f"device={listener.last_device} ({listener.last_device_name})",
        f"rate={listener.last_sample_rate}Hz",
        f"rms={listener.last_rms:.5f}",
        f"peak={listener.last_peak:.5f}",
        f"noise={listener.last_noise_floor:.5f}",
        f"threshold={listener.last_energy_threshold:.5f}",
        f"clipping={listener.last_clipping_ratio * 100:.2f}%",
        f"stt_attempts={listener.last_transcription_attempts}",
        f"error={listener.last_capture_error or 'none'}",
    )
    if listener.last_transcription_rejected_reason:
        print("STT rejected:", listener.last_transcription_rejected_reason)
    if listener.last_clipping_ratio >= 0.01:
        print("MIC LEVEL WARNING: capture is clipping. Lower Windows microphone input level/boost if recognition remains inaccurate.")
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

$tokenProbe = @'
from iras.config import Settings
from iras.cloud_auth import cloud_token_candidates
import httpx
import os

server = os.environ.get("IRAS_VOICE_DOCTOR_SERVER", "").rstrip("/")
settings = Settings.load()
candidates = cloud_token_candidates(settings)
if not candidates:
    print("NONE")
else:
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        for source, token in candidates:
            try:
                response = client.get(
                    server + "/v1/voice/health",
                    headers={"Authorization": "Bearer " + token},
                )
                if response.status_code != 401:
                    print(source + "\t" + token)
                    break
            except Exception:
                print(source + "\t" + token)
                break
        else:
            print("REJECTED")
'@

$env:IRAS_VOICE_DOCTOR_SERVER = $Server
$tokenResult = ($tokenProbe | & $Python -) | Select-Object -Last 1
Remove-Item Env:IRAS_VOICE_DOCTOR_SERVER -ErrorAction SilentlyContinue

if ($tokenResult -eq "NONE") {
    Write-Host "No cloud token found in .env/environment or protected device pairing." -ForegroundColor Yellow
    Write-Host "Render authenticated voice checks are skipped."
    exit 0
}
if ($tokenResult -eq "REJECTED") {
    Write-Host "All available cloud tokens were rejected by Render (401)." -ForegroundColor Red
    Write-Host "Set local IRAS_CLOUD_TOKEN to the exact Render IRAS_API_TOKEN, or re-pair this PC." -ForegroundColor Yellow
    exit 0
}

$parts = $tokenResult -split "`t", 2
$tokenSource = $parts[0]
$token = $parts[1]
Write-Host "Cloud token verified via $tokenSource. Value is intentionally not displayed." -ForegroundColor Green

$headers = @{
    Authorization = "Bearer $token"
}

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
        -UseBasicParsing `
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
