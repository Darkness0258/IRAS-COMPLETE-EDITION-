param([string]$Repo = "D:\Projects\IRAS-complete")
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $Repo).Path
$Base = Join-Path $Repo ".iras_rc91_backup"
if (-not (Test-Path $Base)) { throw "No RC9.1 backup folder found: $Base" }
$Latest = Get-ChildItem $Base -Directory | Sort-Object Name -Descending | Select-Object -First 1
if (-not $Latest) { throw "No RC9.1 backup snapshot found." }
Get-ChildItem $Latest.FullName -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($Latest.FullName.Length).TrimStart('\')
    $dest = Join-Path $Repo $rel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
    Copy-Item $_.FullName $dest -Force
}
Write-Host "Restored RC9.1 backup from $($Latest.FullName)"
