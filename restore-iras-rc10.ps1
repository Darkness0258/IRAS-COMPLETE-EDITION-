param([string]$Repo = "D:\Projects\IRAS-complete")
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $Repo).Path
$BackupRoot = Join-Path $Repo ".iras_rc10_backup"
if (-not (Test-Path $BackupRoot)) { throw "No RC10 backup directory found: $BackupRoot" }
$Latest = Get-ChildItem $BackupRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1
if (-not $Latest) { throw "No RC10 backup snapshot found." }

$Files = @(
  "src\iras\v5\runtime.py",
  "src\iras\tools\v5.py",
  "src\iras\security\tool_content.py",
  "src\iras\persona.py",
  ".env.example"
)
foreach ($Rel in $Files) {
  $Source = Join-Path $Latest.FullName $Rel
  if (Test-Path $Source) {
    $Target = Join-Path $Repo $Rel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
    Copy-Item -Force $Source $Target
  }
}

@(
  "src\iras\v5\web_access.py",
  "tests\test_v500_rc10_full_web_access.py",
  "docs\V5_0_RC10_FULL_WEB_ACCESS.md"
) | ForEach-Object {
  $Target = Join-Path $Repo $_
  if (Test-Path $Target) { Remove-Item -Force $Target }
}
Write-Host "Restored latest pre-RC10 snapshot: $($Latest.FullName)"
