param(
    [string]$Repo = "D:\Projects\IRAS-complete",
    [switch]$Test,
    [switch]$AllowNewer
)

$ErrorActionPreference = "Stop"
Set-Location $Repo

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$argsList = @("$PSScriptRoot\apply_iras_rc6_automation.py", "--repo", $Repo)
if ($Test) { $argsList += "--test" }
if ($AllowNewer) { $argsList += "--allow-newer" }

& $python @argsList
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "RC6 candidate applied. Run full validation:" -ForegroundColor Green
Write-Host "  .\run-v500-validation.ps1"
