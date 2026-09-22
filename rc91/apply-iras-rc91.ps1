param(
    [string]$Repo = "D:\Projects\IRAS-complete",
    [switch]$Test
)
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = (Resolve-Path $Repo).Path

if (-not (Test-Path (Join-Path $Repo "src\iras\voice\multilingual_voice.py"))) {
    Write-Host "RC9 not detected. Applying bundled cumulative RC9 first..."
    & (Join-Path $Here "rc9\apply-iras-rc9.ps1") -Repo $Repo -Test:$Test
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
$argsList = @((Join-Path $Here "apply_iras_rc91_female_roman_urdu.py"), "--repo", $Repo)
if ($Test) { $argsList += "--test" }
& $Python @argsList
exit $LASTEXITCODE
