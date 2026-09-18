$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .\.venv\Scripts\iras.exe)) {
    throw "IRAS is not installed. Run .\install.ps1 first."
}

$autoVision = $true
if ($env:IRAS_OMNIPARSER_AUTOSTART -and $env:IRAS_OMNIPARSER_AUTOSTART.ToLowerInvariant() -in @('0','false','no','off')) {
    $autoVision = $false
}

if ($autoVision) {
    & .\.venv\Scripts\iras.exe --vision-start
    $visionExit = $LASTEXITCODE
    if ($visionExit -ne 0) {
        # The managed-runtime CLI deliberately returns non-zero for missing,
        # unhealthy, or reachable-but-unowned local services. Provision/repair
        # through the idempotent bootstrap instead of silently attaching to a
        # legacy process. Existing unmanaged trees are preserved.
        Write-Host "Managed OmniParser is unavailable or not IRAS-owned. Running provisioning/repair..." -ForegroundColor Yellow
        & .\setup-omniparser.ps1 -Repair
        if ($LASTEXITCODE -ne 0) { throw "OmniParser setup failed. See $HOME\.iras\omniparser\omniparser.log" }
        & .\.venv\Scripts\iras.exe --vision-start
        if ($LASTEXITCODE -ne 0) { throw "IRAS-managed OmniParser failed its post-provision start check." }
    }
}

& .\.venv\Scripts\iras.exe
exit $LASTEXITCODE
