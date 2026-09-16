$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-IrasCleanup {
    & .\scripts\maintenance\clean-v400-validation-debris.ps1 -Quiet
}

Write-Host "=== IRAS v4.2 RC5 MULTI-AGENT VALIDATION ==="
Write-Host ""
Invoke-IrasCleanup
Write-Host "IRAS validation debris cleanup: PASS"

try {
    python .\scripts\validate_v420_clean_tree.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    python .\scripts\validate_v420_integrated.py
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
    Write-Host "IRAS v4.2 RC5 VALIDATION RESULT: PASS"
}
finally {
    Invoke-IrasCleanup
}
