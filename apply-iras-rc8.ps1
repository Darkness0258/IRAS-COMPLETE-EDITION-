param(
    [string]$Repo = "D:\Projects\IRAS-complete",
    [switch]$Test = $true
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $Repo).Path

Write-Host "=== IRAS RC8 Production Strengthening Update ===" -ForegroundColor Cyan
Write-Host "Repository: $Repo"

$cognition = Join-Path $Repo "src\iras\v5\cognitive_core.py"
if (-not (Test-Path $cognition)) {
    Write-Host "RC7 is not present. Applying bundled cumulative RC6 + RC7 first..." -ForegroundColor Yellow
    & "$PSScriptRoot\rc7\apply-iras-rc7.ps1" -Repo $Repo -Test:$Test
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$argsList = @("$PSScriptRoot\apply_iras_rc8_strengthening.py", "--repo", $Repo)
if ($Test) { $argsList += "--test" }
python @argsList
exit $LASTEXITCODE
