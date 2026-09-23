$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$VenvPath = Join-Path $PSScriptRoot ".venv"
$Python = Join-Path $VenvPath "Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "IRAS virtual environment Python not found: $Python"
}

function Test-InVenv {
    param([string]$Path)

    $venvPrefix = $VenvPath.TrimEnd('\') + '\'

    return $Path.StartsWith(
        $venvPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Invoke-IrasCleanup {
    # Remove Python/runtime caches outside .venv only.
    Get-ChildItem -Path $PSScriptRoot -Recurse -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object {
            -not (Test-InVenv $_.FullName) -and
            $_.Name -in @(
                '__pycache__',
                '.pytest_cache',
                '.mypy_cache',
                '.ruff_cache'
            )
        } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    # Remove compiled Python files outside .venv only.
    Get-ChildItem -Path $PSScriptRoot -Recurse -File -Include *.pyc,*.pyo -ErrorAction SilentlyContinue |
        Where-Object {
            -not (Test-InVenv $_.FullName)
        } |
        Remove-Item -Force -ErrorAction SilentlyContinue

    # Remove reproducible build artifacts outside .venv only.
    Get-ChildItem -Path $PSScriptRoot -Recurse -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object {
            -not (Test-InVenv $_.FullName) -and (
                $_.Name -in @('build','dist') -or
                $_.Name.EndsWith(
                    '.egg-info',
                    [System.StringComparison]::OrdinalIgnoreCase
                )
            )
        } |
        Sort-Object { $_.FullName.Length } -Descending |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "=== IRAS v5.0 RC12 COMPLETE OPERATING LAYER VALIDATION ==="
Write-Host "Python: $Python"

Invoke-IrasCleanup

try {
    & $Python .\scripts\validate_v500_clean_tree.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""

    & $Python .\scripts\validate_v500_integrated.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    Write-Host "=== PYTHON COMPILE VALIDATION ==="

    & $Python -m compileall -q .\src .\tests .\scripts
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "PYTHON COMPILE VALIDATION: PASS"

    Write-Host ""
    Write-Host "=== FULL REGRESSION + V5 FEATURE SUITE ==="

    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    Write-Host "IRAS v5.0 RC12 VALIDATION RESULT: PASS"
}
finally {
    Invoke-IrasCleanup
}