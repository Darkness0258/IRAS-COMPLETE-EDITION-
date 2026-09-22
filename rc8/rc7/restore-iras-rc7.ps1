param(
    [string]$Repo = "D:\Projects\IRAS-complete"
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $Repo).Path
$backupRoot = Join-Path $Repo ".iras_rc7_backup"
if (-not (Test-Path $backupRoot)) {
    throw "No .iras_rc7_backup directory exists in $Repo"
}
$backup = Get-ChildItem $backupRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1
if (-not $backup) { throw "No RC7 backup was found." }

$restore = @(
    "src\iras\v5\runtime.py",
    "src\iras\tools\v5.py"
)
foreach ($relative in $restore) {
    $source = Join-Path $backup.FullName $relative
    $target = Join-Path $Repo $relative
    if (Test-Path $source) {
        Copy-Item $source $target -Force
        Write-Host "Restored $relative"
    }
}

@(
    "src\iras\v5\cognitive_core.py",
    "tests\test_v500_rc7_cognitive_core.py",
    "docs\V5_0_RC7_COGNITIVE_CORE.md"
) | ForEach-Object {
    $target = Join-Path $Repo $_
    if (Test-Path $target) { Remove-Item $target -Force; Write-Host "Removed $_" }
}

Write-Host "RC7 cognitive core rollback complete." -ForegroundColor Green
Write-Host "If this package also installed RC6 and you want to remove RC6 too, run rc6\restore-iras-rc6.ps1 separately."
