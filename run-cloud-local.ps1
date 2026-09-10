$ErrorActionPreference = "Stop"
if (-not (Test-Path ".venv")) { python -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[cloud,dev]"
Write-Host "Starting IRAS Cloud on http://127.0.0.1:8765"
iras-cloud
