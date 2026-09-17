$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== IRAS v4.4.0 FINAL REAL-DEVICE PRECHECK ==="

$configPath = Join-Path $HOME ".iras-device-bridge.json"
if (-not (Test-Path $configPath)) {
    throw "IRAS device bridge is not configured: $configPath"
}
$config = Get-Content $configPath -Raw | ConvertFrom-Json
$server = [string]$config.server_url
if (-not $server) { throw "IRAS device bridge has no server_url." }

$health = Invoke-RestMethod ($server.TrimEnd('/') + "/health")
if ($health.version -ne "4.4.0") { throw "Expected IRAS 4.4.0, got $($health.version)." }
if ([int]$health.remote_protocol -ne 1) { throw "Expected remote protocol 1." }
Write-Host "Cloud health/version: PASS"

$task = Get-ScheduledTask -TaskName "IRAS Remote Windows Agent" -ErrorAction Stop
if ($task.State -ne "Running") {
    Start-ScheduledTask -TaskName "IRAS Remote Windows Agent"
    Start-Sleep -Seconds 3
    $task = Get-ScheduledTask -TaskName "IRAS Remote Windows Agent"
}
if ($task.State -ne "Running") { throw "IRAS Remote Windows Agent is not running." }
Write-Host "Remote bridge task: PASS"

& iras --doctor
if ($LASTEXITCODE -ne 0) { throw "iras --doctor reported a failure." }
Write-Host "Doctor: PASS"

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    $models = & ollama list
    if ($LASTEXITCODE -ne 0) { throw "ollama list failed." }
    Write-Host "Ollama command: PASS"
    $models | Select-Object -First 8 | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "Ollama command: WARN (not installed in PATH)"
}

Write-Host ""
Write-Host "IRAS v4.4.0 FINAL REAL-DEVICE PRECHECK: PASS"
Write-Host "Next: open the Providers panel and click 'Probe Now', then run one engineering goal and one concurrent app-open command."
