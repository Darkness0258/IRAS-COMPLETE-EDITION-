$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

# User state lives outside the package tree (~/.iras, ~/.iras-device-bridge.json,
# .env), so reinstalling code does not erase pairings, DPAPI secrets, skills, or
# local safety policy.
python -m pip install -e ".[voice,browser]"
if ($LASTEXITCODE -ne 0) { throw "IRAS package update failed." }
.\run-v400-validation.ps1
if ($LASTEXITCODE -ne 0) { throw "IRAS v4 validation failed; do not replace a known-good deployment." }
Write-Host "IRAS update validated successfully." -ForegroundColor Green
