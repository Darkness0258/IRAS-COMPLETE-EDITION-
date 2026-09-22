param(
    [string]$Repo = "D:\Projects\IRAS-complete",
    [string]$Backup = ""
)

$ErrorActionPreference = "Stop"
$backupRoot = Join-Path $Repo ".iras_rc6_backup"
if (-not $Backup) {
    $latest = Get-ChildItem $backupRoot -Directory -ErrorAction Stop |
        Sort-Object Name -Descending |
        Select-Object -First 1
    if (-not $latest) { throw "No RC6 backup found under $backupRoot" }
    $Backup = $latest.FullName
}

$restore = @(
    "src\iras\v5\runtime.py",
    "src\iras\bootstrap.py",
    "src\iras\tools\v5.py",
    "src\iras\v5\voice_runtime.py",
    "src\iras\voice\stt.py"
)
foreach ($relative in $restore) {
    $src = Join-Path $Backup $relative
    $dst = Join-Path $Repo $relative
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        Write-Host "Restored $relative"
    }
}

$remove = @(
    "src\iras\v5\automation_engine.py",
    "tests\test_v500_rc6_automation_voice.py",
    "docs\V5_0_RC6_AUTOMATION_VOICE.md"
)
foreach ($relative in $remove) {
    $dst = Join-Path $Repo $relative
    if (Test-Path $dst) {
        Remove-Item $dst -Force
        Write-Host "Removed $relative"
    }
}

Write-Host "RC6 candidate files restored from $Backup" -ForegroundColor Green
