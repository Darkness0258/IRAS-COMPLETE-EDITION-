param(
    [switch]$AllFeatures,
    [switch]$InstallBrowser
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$python = (Get-Command python -ErrorAction Stop).Source
$extra = if ($AllFeatures) { ".[all]" } else { ".[voice,browser]" }
& $python -m pip install -e $extra
if ($LASTEXITCODE -ne 0) { throw "IRAS installation failed." }

if ($InstallBrowser) {
    & $python -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "Playwright Chromium installation failed." }
}

Write-Host "Running IRAS production doctor..." -ForegroundColor Cyan
& iras --doctor
Write-Host "IRAS v4 installation/update completed." -ForegroundColor Green
Write-Host "For secure worldwide access run: .\setup-remote-windows.ps1 -FullFileSystem"
