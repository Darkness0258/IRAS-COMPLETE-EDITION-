param(
    [switch]$NoRestartRemoteTask
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$TaskName = "IRAS Remote Windows Agent"
$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$VenvScripts = Join-Path $PSScriptRoot ".venv\Scripts"

if (-not (Test-Path $VenvPython)) {
    throw "IRAS virtual environment is missing at $VenvPython. Run .\install.ps1 first."
}

$taskExists = $false
$taskWasRunning = $false
try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $taskExists = $true
    $taskWasRunning = ($task.State -eq "Running")
    if ($taskWasRunning) {
        Write-Host "Stopping $TaskName so pip can replace iras-device.exe..." -ForegroundColor Yellow
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 800
    }
} catch {
    $taskExists = $false
}

# Console-script wrappers are Windows executables. A running wrapper can keep
# itself locked even after its Scheduled Task parent stops. Terminate only IRAS
# wrappers from this project's venv; unrelated Python/PowerShell processes are
# deliberately left alone.
try {
    Get-Process -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $path = $_.Path
            if ($path -and $path.StartsWith($VenvScripts, [System.StringComparison]::OrdinalIgnoreCase) -and $_.Name -like "iras*") {
                Write-Host "Stopping locked IRAS process $($_.Name) ($($_.Id))..." -ForegroundColor Yellow
                Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    }
    Start-Sleep -Milliseconds 500
} catch {}

Write-Host "Repairing editable IRAS installation..." -ForegroundColor Cyan
& $VenvPython -m pip install -e ".[all,cloud]"
if ($LASTEXITCODE -ne 0) {
    throw "IRAS editable install failed."
}

Write-Host "Verifying IRAS import and protocol..." -ForegroundColor Cyan
& $VenvPython -c "import iras; from iras.remote_protocol import REMOTE_PROTOCOL_VERSION; print('IRAS', iras.__version__, 'Remote Protocol', REMOTE_PROTOCOL_VERSION)"
if ($LASTEXITCODE -ne 0) {
    throw "IRAS import verification failed after reinstall."
}

$irasExe = Join-Path $VenvScripts "iras.exe"
$deviceExe = Join-Path $VenvScripts "iras-device.exe"
if (-not (Test-Path $irasExe)) { throw "iras.exe was not recreated." }
if (-not (Test-Path $deviceExe)) { throw "iras-device.exe was not recreated." }

if ($taskExists -and $taskWasRunning -and -not $NoRestartRemoteTask) {
    Write-Host "Restarting $TaskName..." -ForegroundColor Cyan
    Start-ScheduledTask -TaskName $TaskName
}

Write-Host "IRAS local installation repaired successfully." -ForegroundColor Green
Write-Host "Next: .\voice-doctor.ps1 -TestMicrophone"
Write-Host "Then: .\run-iras.ps1 or iras-desktop"
