$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .\.venv\Scripts\python.exe)) {
    throw "IRAS virtual environment is missing. Run .\install.ps1 first."
}

# A Windows console-script wrapper may survive while the editable package was
# partially uninstalled (for example when the remote bridge locked
# iras-device.exe during pip install). Verify the import, not only iras.exe.
& .\.venv\Scripts\python.exe -c "import iras" 2>$null
if ($LASTEXITCODE -ne 0 -or -not (Test-Path .\.venv\Scripts\iras.exe)) {
    Write-Host "IRAS package installation is incomplete. Running safe local repair..." -ForegroundColor Yellow
    & .\repair-local-install.ps1
    if ($LASTEXITCODE -ne 0) { throw "IRAS local package repair failed." }
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
