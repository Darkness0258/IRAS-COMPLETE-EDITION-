param(
    [string]$Repo = "D:\Projects\IRAS-complete",
    [switch]$Test = $true
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path $Repo).Path

Write-Host "=== IRAS RC7 Cognitive Core Update ===" -ForegroundColor Cyan
Write-Host "Repository: $Repo"

$automationEngine = Join-Path $Repo "src\iras\v5\automation_engine.py"
if (-not (Test-Path $automationEngine)) {
    Write-Host "RC6 is not present. Applying bundled RC6 automation + wake voice first..." -ForegroundColor Yellow
    $rc6Args = @("$PSScriptRoot\rc6\apply_iras_rc6_automation.py", "--repo", $Repo)
    if ($Test) { $rc6Args += "--test" }
    python @rc6Args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$argsList = @("$PSScriptRoot\apply_iras_rc7_cognitive.py", "--repo", $Repo)
if ($Test) { $argsList += "--test" }
python @argsList
exit $LASTEXITCODE
