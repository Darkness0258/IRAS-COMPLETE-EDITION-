$ErrorActionPreference = "Stop"
Write-Host "Installing IRAS 1.1 (OpenRouter-first)..."
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env. Add your OPENROUTER_API_KEY before starting IRAS." -ForegroundColor Yellow
}
Write-Host "Install complete."
Write-Host "1. Edit .env and set OPENROUTER_API_KEY=..."
Write-Host "2. Optional: change IRAS_MODEL=openrouter/free"
Write-Host "3. Run: .\.venv\Scripts\iras.exe --doctor"
Write-Host "4. Run: .\run-iras.ps1"
