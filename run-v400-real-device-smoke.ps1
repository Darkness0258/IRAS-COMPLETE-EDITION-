$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python .\scripts\validate_v400_real_device.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
