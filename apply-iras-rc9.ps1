param(
    [string]$Repo = "D:\Projects\IRAS-complete",
    [switch]$Test = $true
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $Repo).Path

Write-Host "=== IRAS RC9 Multilingual Voice & Language Intelligence ===" -ForegroundColor Cyan
Write-Host "Repository: $Repo"

$rc8 = Join-Path $Repo "src\iras\v5\strengthening_core.py"
if (-not (Test-Path $rc8)) {
    Write-Host "RC8 is not present. Applying bundled cumulative RC6 + RC7 + RC8 first..." -ForegroundColor Yellow
    & "$PSScriptRoot\rc8\apply-iras-rc8.ps1" -Repo $Repo -Test:$Test
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$argsList = @("$PSScriptRoot\apply_iras_rc9_multilingual.py", "--repo", $Repo)
if ($Test) { $argsList += "--test" }
& $python @argsList
exit $LASTEXITCODE
