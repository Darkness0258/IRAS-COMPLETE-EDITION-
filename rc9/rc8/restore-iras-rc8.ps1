param(
    [string]$Repo = "D:\Projects\IRAS-complete"
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $Repo).Path
$backupRoot = Join-Path $Repo ".iras_rc8_backup"
if (-not (Test-Path $backupRoot)) {
    throw "No .iras_rc8_backup folder exists in $Repo"
}
$latest = Get-ChildItem $backupRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1
if (-not $latest) { throw "No RC8 backup snapshot found." }

Write-Host "Restoring RC8-modified files from $($latest.FullName)" -ForegroundColor Yellow
$relative = @(
    "src\iras\v5\runtime.py",
    "src\iras\tools\v5.py",
    "src\iras\cloud_api.py"
)
foreach ($item in $relative) {
    $source = Join-Path $latest.FullName $item
    if (Test-Path $source) {
        $target = Join-Path $Repo $item
        Copy-Item $source $target -Force
    }
}

@(
    "src\iras\v5\strengthening_core.py",
    "tests\test_v500_rc8_strengthening.py",
    "docs\V5_0_RC8_STRENGTHENING.md"
) | ForEach-Object {
    $path = Join-Path $Repo $_
    if (Test-Path $path) { Remove-Item $path -Force }
}
Write-Host "RC8 overlay restored. RC6/RC7 remain installed." -ForegroundColor Green
