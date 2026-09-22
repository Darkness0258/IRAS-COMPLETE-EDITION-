param(
    [string]$Repo = "D:\Projects\IRAS-complete",
    [string]$Backup = ""
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $Repo).Path
$backupRoot = Join-Path $Repo ".iras_rc9_backup"
if (-not $Backup) {
    $candidate = Get-ChildItem $backupRoot -Directory -ErrorAction Stop | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $candidate) { throw "No RC9 backup found under $backupRoot" }
    $Backup = $candidate.FullName
}
$Backup = (Resolve-Path $Backup).Path
Write-Host "Restoring RC9-modified files from $Backup" -ForegroundColor Yellow
Get-ChildItem $Backup -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($Backup.Length).TrimStart('\','/')
    $dest = Join-Path $Repo $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
    Copy-Item $_.FullName $dest -Force
}
$created = @(
    "src\iras\voice\multilingual_voice.py",
    "tests\test_v500_rc9_multilingual_voice.py",
    "docs\V5_0_RC9_MULTILINGUAL_VOICE.md"
)
foreach ($relative in $created) {
    $original = Join-Path $Backup $relative
    if (-not (Test-Path $original)) {
        $dest = Join-Path $Repo $relative
        if (Test-Path $dest) { Remove-Item $dest -Force }
    }
}
Write-Host "RC9 overlay restored. Earlier RC6-RC8 layers remain installed." -ForegroundColor Green
