$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e ".[cloud,dev]"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ""
    Write-Host "Created .env from .env.example."
    Write-Host "Add OPENROUTER_API_KEY, IRAS_API_TOKEN, and DATABASE_URL before cloud testing."
    exit 0
}

Write-Host "Starting IRAS Cloud locally..."
iras-cloud
