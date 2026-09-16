param(
    [string]$ServerUrl = "",
    [ValidateSet("read_only", "control", "full")]
    [string]$Mode = "full",
    [switch]$AllowPower,
    [switch]$AllowCommand,
    [switch]$FullFileSystem,
    [string[]]$AllowedRoot = @(),
    [switch]$NoStartupTask
)

$ErrorActionPreference = "Stop"
$TaskName = "IRAS Remote Windows Agent"

if (-not $ServerUrl) {
    $ServerUrl = Read-Host "IRAS Cloud HTTPS URL (for example https://iras-cloud.onrender.com)"
}
if ($ServerUrl -match "YOUR-IRAS-CLOUD|YOUR-ACTUAL-RENDER-URL|example\.?$") {
    throw "Replace the placeholder ServerUrl with your real deployed IRAS URL, for example https://iras-cloud-xxxx.onrender.com."
}
if (-not ($ServerUrl.StartsWith("https://") -or $ServerUrl.StartsWith("http://127.0.0.1") -or $ServerUrl.StartsWith("http://localhost"))) {
    throw "Remote IRAS requires HTTPS. localhost is allowed only for testing."
}
$ServerUrl = $ServerUrl.TrimEnd('/')

# Fail fast before asking for any secret. This catches stale/wrong Render services
# and gives a useful error instead of accepting a token for an incompatible cloud.
try {
    $health = Invoke-RestMethod -Uri ($ServerUrl + "/health") -Method Get -TimeoutSec 15 -ErrorAction Stop
} catch {
    throw "IRAS Cloud health check failed at $ServerUrl/health. Confirm the Render service is live and the URL is correct. $($_.Exception.Message)"
}
if (-not $health.ok) {
    throw "IRAS Cloud /health did not report ok=true. Redeploy the v4 cloud backend before pairing Windows."
}
if (-not $health.version -or $health.version -notmatch '^4\.') {
    throw "The configured server is not running the v4 remote backend (version=$($health.version)). Redeploy the current IRAS v4 release to Render."
}
if (-not $health.service_id -or $health.service_id -ne "iras-cloud") {
    throw "The configured server is not running the v4 remote backend (service_id=$($health.service_id)). Redeploy the current IRAS v4 release to Render."
}
if ($null -eq $health.remote_protocol -or [int]$health.remote_protocol -ne 1) {
    throw "The configured server has an incompatible IRAS remote protocol (server=$($health.remote_protocol), required=1). Redeploy the current IRAS v4 release to Render."
}

$secureToken = Read-Host "IRAS_API_TOKEN (32+ random characters)" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
if ($plainToken.Length -lt 32) {
    throw "IRAS_API_TOKEN is too short for remote administration."
}

# Console-script entry points can disappear from PATH after Python upgrades or
# user/system install changes. Fall back to the importable Python module so the
# same installed IRAS package still works and the startup task remains durable.
$deviceCommand = Get-Command iras-device -ErrorAction SilentlyContinue
$devicePrefixArgs = @()
$taskArgument = $null
if ($deviceCommand) {
    $deviceExe = $deviceCommand.Source
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
    }
    if (-not $pythonCommand) {
        throw "Neither iras-device nor Python is available on PATH. Reinstall IRAS before configuring remote access."
    }
    $deviceExe = $pythonCommand.Source
    $devicePrefixArgs = @("-m", "iras.device_bridge.agent")
    $taskArgument = '-m iras.device_bridge.agent'
}

$irasExe = (Get-Command iras -ErrorAction Stop).Source

$oldServer = $env:IRAS_SERVER_URL
$oldToken = $env:IRAS_API_TOKEN
try {
    $env:IRAS_SERVER_URL = $ServerUrl
    $env:IRAS_API_TOKEN = $plainToken
    $configureArgs = @("--configure", "--server-url", $ServerUrl)
    if ($FullFileSystem) {
        $roots = @("C:\")
        if (Test-Path "D:\") { $roots += "D:\" }
        foreach ($root in $roots) { $configureArgs += @("--allowed-root", $root) }
    } elseif ($AllowedRoot.Count -gt 0) {
        foreach ($root in $AllowedRoot) { $configureArgs += @("--allowed-root", $root) }
    }
    & $deviceExe @devicePrefixArgs @configureArgs
    if ($LASTEXITCODE -ne 0) { throw "iras-device configuration failed." }
} finally {
    $env:IRAS_SERVER_URL = $oldServer
    $env:IRAS_API_TOKEN = $oldToken
    $plainToken = $null
}

$armArgs = @("--remote-arm", $Mode, "--remote-persistent")
if ($AllowPower) { $armArgs += "--remote-allow-power" }
if ($AllowCommand) { $armArgs += "--remote-allow-shell" }
& $irasExe @armArgs
if ($LASTEXITCODE -ne 0) { throw "Failed to arm IRAS remote policy." }

if (-not $NoStartupTask) {
    # Keep the bridge in the interactive user session (required for screenshots/UI
    # control) while hiding its long-running console window. PowerShell remains the
    # scheduled process and waits for the bridge child, so Task Scheduler can still
    # supervise/restart it normally.
    $escapedDeviceExe = $deviceExe.Replace("'", "''")
    if ($taskArgument) {
        $bridgeCommand = "& '$escapedDeviceExe' $taskArgument"
    } else {
        $bridgeCommand = "& '$escapedDeviceExe'"
    }
    $encodedBridgeCommand = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($bridgeCommand)
    )
    $hiddenTaskArgs = "-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand $encodedBridgeCommand"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $hiddenTaskArgs
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Days 3650) -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "IRAS outbound-only authenticated remote Windows bridge" -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
}

Write-Host ""
Write-Host "IRAS remote Windows access configured." -ForegroundColor Green
Write-Host "Server: $ServerUrl"
Write-Host "Cloud: $($health.version) / remote protocol $($health.remote_protocol)"
Write-Host "Local policy mode: $Mode"
Write-Host "Scheduled task: $(-not $NoStartupTask)"
Write-Host "Full filesystem roots: $FullFileSystem"
Write-Host "No inbound Windows port was opened. The laptop connects outbound to IRAS Cloud."
Write-Host "Remote-only stop: iras --remote-disarm"
Write-Host "Controller emergency stop: iras --emergency-stop"
Write-Host "For 24/7 reachability, configure Windows sleep separately; this script does not weaken lock/UAC/security settings."
