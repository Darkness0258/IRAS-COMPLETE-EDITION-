param(
    [string]$Repo = "D:\Projects\IRAS-complete",
    [switch]$Test
)
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = (Resolve-Path $Repo).Path

$VoiceFile = Join-Path $Repo "src\iras\voice\multilingual_voice.py"
$NeedRC91 = -not (Test-Path $VoiceFile)
if (-not $NeedRC91) {
    $NeedRC91 = -not (Select-String -Path $VoiceFile -SimpleMatch '"default_text_style": "roman-urdu"' -Quiet)
}
if ($NeedRC91) {
    Write-Host "RC9.1 not detected. Applying bundled cumulative RC9.1 first..."
    & (Join-Path $Here "rc91\apply-iras-rc91.ps1") -Repo $Repo -Test:$Test
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
$argsList = @((Join-Path $Here "apply_iras_rc10_full_web.py"), "--repo", $Repo)
if ($Test) { $argsList += "--test" }
& $Python @argsList
exit $LASTEXITCODE
