$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$oldDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
$env:PYTHONDONTWRITEBYTECODE = "1"

function Invoke-IRASArtifactCleanup {
    python .\scripts\cleanup_v400_runtime_artifacts.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

try {
    Write-Host "=== IRAS v4.0 RC1 PRODUCTION VALIDATION ==="
    Write-Host ""

    # Existing developer checkouts may contain caches or packaging metadata from
    # pytest, compileall, editable installs, or wheel builds. Remove only generated
    # artifacts before checking the release tree; user state/.env/.git/venvs are
    # untouched.
    Invoke-IRASArtifactCleanup

    python .\scripts\validate_v400_clean_tree.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    python .\scripts\validate_v400_integrated.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    Write-Host "=== PYTHON COMPILE VALIDATION ==="
    python -m compileall -q .\src .\tests .\scripts
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "PYTHON COMPILE VALIDATION: PASS"

    # compileall deliberately writes bytecode. Remove it before pytest and keep
    # pytest's cache provider disabled so the checkout finishes clean too.
    Invoke-IRASArtifactCleanup

    Write-Host ""
    Write-Host "=== FULL REGRESSION SUITE ==="
    python -m pytest -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Invoke-IRASArtifactCleanup

    Write-Host ""
    Write-Host "=== FINAL CLEAN TREE RECHECK ==="
    python .\scripts\validate_v400_clean_tree.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    Write-Host "IRAS v4.0 RC1 VALIDATION RESULT: PASS"
}
finally {
    # Best effort cleanup even when a validation stage fails.
    try {
        python .\scripts\cleanup_v400_runtime_artifacts.py | Out-Host
    } catch {
        Write-Warning "Unable to remove one or more generated validation artifacts: $($_.Exception.Message)"
    }

    if ($null -eq $oldDontWriteBytecode) {
        Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONDONTWRITEBYTECODE = $oldDontWriteBytecode
    }
}
