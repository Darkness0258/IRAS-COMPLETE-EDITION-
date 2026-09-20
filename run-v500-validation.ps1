$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-IrasCleanup {
    # Python/runtime caches.
    Get-ChildItem -Path . -Recurse -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -in @('__pycache__','.pytest_cache','.mypy_cache','.ruff_cache') } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Recurse -File -Include *.pyc,*.pyo -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue

    # Editable installs (`pip install -e .`) legitimately generate source-tree
    # package metadata. Build tools may also leave build/dist directories.
    # These are reproducible local artifacts, not release source, so remove
    # them before clean-tree validation and after the suite finishes.
    Get-ChildItem -Path . -Recurse -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -in @('build','dist') -or
            $_.Name.EndsWith('.egg-info',[System.StringComparison]::OrdinalIgnoreCase)
        } |
        Sort-Object { $_.FullName.Length } -Descending |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "=== IRAS v5.0 RC4 COMPLETE OPERATING LAYER VALIDATION ==="
Invoke-IrasCleanup
try {
    python .\scripts\validate_v500_clean_tree.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host ""
    python .\scripts\validate_v500_integrated.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host ""
    Write-Host "=== PYTHON COMPILE VALIDATION ==="
    python -m compileall -q .\src .\tests .\scripts
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "PYTHON COMPILE VALIDATION: PASS"
    Write-Host ""
    Write-Host "=== FULL REGRESSION + V5 FEATURE SUITE ==="
    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host ""
    Write-Host "IRAS v5.0 RC4 VALIDATION RESULT: PASS"
}
finally { Invoke-IrasCleanup }
