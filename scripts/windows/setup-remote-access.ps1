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
if ($ServerUrl -match "YOUR-IRAS-CLOUD|example\.?$") {
    throw "Replace the placeholder ServerUrl with your real deployed IRAS URL, for example https://iras-cloud-xxxx.onrender.com."
}
if (-not ($ServerUrl.StartsWith("https://") -or $ServerUrl.StartsWith("http://127.0.0.1") -or $ServerUrl.StartsWith("http://localhost"))) {
    throw "Remote IRAS requires HTTPS. localhost is allowed only for testing."
}
$ServerUrl = $ServerUrl.TrimEnd('/')

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

$deviceExe = (Get-Command iras-device -ErrorAction Stop).Source
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
    & $deviceExe @configureArgs
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
    $action = New-ScheduledTaskAction -Execute $deviceExe
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Days 3650) -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "IRAS outbound-only authenticated remote Windows bridge" -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
}

Write-Host ""
Write-Host "IRAS remote Windows access configured." -ForegroundColor Green
Write-Host "Server: $ServerUrl"
Write-Host "Local policy mode: $Mode"
Write-Host "Scheduled task: $(-not $NoStartupTask)"
Write-Host "Full filesystem roots: $FullFileSystem"
Write-Host "No inbound Windows port was opened. The laptop connects outbound to IRAS Cloud."
Write-Host "Remote-only stop: iras --remote-disarm"
Write-Host "Controller emergency stop: iras --emergency-stop"
Write-Host "For 24/7 reachability, configure Windows sleep separately; this script does not weaken lock/UAC/security settings."
