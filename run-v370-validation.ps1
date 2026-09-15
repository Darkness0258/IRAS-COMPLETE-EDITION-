$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== IRAS v3.7.0 MULTIMODAL VALIDATION ==="
Write-Host ""
python .\scripts\validate_v370_clean_tree.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
python .\scripts\validate_v370_integrated.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "=== PYTHON COMPILE VALIDATION ==="
python -m compileall -q .\src .\scripts
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "PYTHON COMPILE VALIDATION: PASS"

Write-Host ""
Write-Host "=== FULL REGRESSION SUITE ==="
python -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "IRAS v3.7.0 VALIDATION RESULT: PASS"
