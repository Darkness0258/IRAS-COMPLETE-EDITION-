param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$removedDirs = 0
$removedFiles = 0

$dirNames = @("__pycache__", ".pytest_cache", "build", "dist")
Get-ChildItem -Path $Root -Directory -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $dirNames -contains $_.Name -or $_.Name -like "*.egg-info" } |
    Sort-Object FullName -Descending |
    ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path -LiteralPath $_.FullName)) { $removedDirs++ }
    }

Get-ChildItem -Path $Root -File -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -eq ".pyc" -or $_.Name -eq ".coverage" } |
    ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path -LiteralPath $_.FullName)) { $removedFiles++ }
    }

if (-not $Quiet) {
    Write-Host "IRAS validation debris cleanup: directories=$removedDirs files=$removedFiles"
}
