$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Installing IRAS v5.0.0 RC12 Complete Operating Layer..." -ForegroundColor Cyan
if (-not (Test-Path .\.venv\Scripts\python.exe)) {
    Write-Host "Creating IRAS virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the IRAS virtual environment." }
} else {
    Write-Host "Reusing existing IRAS virtual environment." -ForegroundColor DarkGray
}
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e ".[all,cloud]"
if ($LASTEXITCODE -ne 0) { throw "IRAS dependency installation failed." }

Write-Host "Installing Playwright Chromium runtime..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Playwright Chromium installation failed." }

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env. Configure your preferred brain provider/secrets before cloud use." -ForegroundColor Yellow
}

Write-Host "Provisioning IRAS-managed OmniParser vision runtime..." -ForegroundColor Cyan
& .\setup-omniparser.ps1
if ($LASTEXITCODE -ne 0) { throw "OmniParser provisioning failed." }

Write-Host "Running local health checks..." -ForegroundColor Cyan
.\.venv\Scripts\iras.exe --doctor

Write-Host "Install complete." -ForegroundColor Green
Write-Host "Run IRAS with: .\run-iras.ps1"
