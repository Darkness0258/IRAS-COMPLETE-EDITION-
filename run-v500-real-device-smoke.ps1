$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "=== IRAS v5.0 RC3 REAL-DEVICE PRECHECK ==="
python -m iras --version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
iras --doctor
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -c "from iras.v5.runtime import build_v5_runtime; r=build_v5_runtime(); s=r.status(); assert s['feature_count']==27; print('V5 capability runtime:', s['feature_count'], 'systems PASS')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "IRAS v5.0 RC3 REAL-DEVICE PRECHECK: PASS"
Write-Host "Next: when API quotas are available, run the deferred real-device/API acceptance suite. Local/offline build contracts can be validated now."
