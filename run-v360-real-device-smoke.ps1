$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== IRAS v3.6.0 READ-ONLY REAL DEVICE SMOKE TEST ==="
python .\scripts\validate_v360_real_device.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
