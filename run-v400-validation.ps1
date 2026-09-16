$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$oldDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
$oldPythonPath = $env:PYTHONPATH
$env:PYTHONDONTWRITEBYTECODE = "1"
$sourcePath = Join-Path $PSScriptRoot "src"
if ([string]::IsNullOrWhiteSpace($oldPythonPath)) {
    $env:PYTHONPATH = $sourcePath
} else {
    $env:PYTHONPATH = $sourcePath + [IO.Path]::PathSeparator + $oldPythonPath
}

function Invoke-IRASCacheCleanup {
    python .\scripts\cleanup_v400_runtime_artifacts.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

try {
    Write-Host "=== IRAS v4.0 RC1 PRODUCTION VALIDATION ==="
    Write-Host ""

    # Existing developer checkouts may contain caches from a previous pytest or
    # compileall run. Remove only generated cache artifacts before checking the
    # release tree; user state/.env/.git/venvs are untouched.
    Invoke-IRASCacheCleanup

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
    Invoke-IRASCacheCleanup

    Write-Host ""
    Write-Host "=== FULL REGRESSION SUITE ==="
    python -m pytest -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Invoke-IRASCacheCleanup

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
        Write-Warning "Unable to remove one or more generated validation caches: $($_.Exception.Message)"
    }

    if ($null -eq $oldDontWriteBytecode) {
        Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONDONTWRITEBYTECODE = $oldDontWriteBytecode
    }

    if ($null -eq $oldPythonPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONPATH = $oldPythonPath
    }
}
