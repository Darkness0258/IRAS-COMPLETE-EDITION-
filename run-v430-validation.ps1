$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-IrasCleanup {
    & .\scripts\maintenance\clean-v400-validation-debris.ps1 -Quiet
}

Write-Host "=== IRAS v4.3 RC4 ENGINEERING DAG ENFORCEMENT VALIDATION ==="
Write-Host ""
Invoke-IrasCleanup
Write-Host "IRAS validation debris cleanup: PASS"

try {
    python .\scripts\validate_v430_clean_tree.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    python .\scripts\validate_v430_integrated.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    Write-Host "=== PYTHON COMPILE VALIDATION ==="
    python -m compileall -q .\src .\tests .\scripts
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "PYTHON COMPILE VALIDATION: PASS"

    Write-Host ""
    Write-Host "=== FULL REGRESSION SUITE ==="
    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    Write-Host "IRAS v4.3 RC4 VALIDATION RESULT: PASS"
}
finally {
    Invoke-IrasCleanup
}
