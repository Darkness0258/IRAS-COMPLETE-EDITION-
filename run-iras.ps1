$ErrorActionPreference = "Stop"
if (-not (Test-Path .\.venv\Scripts\iras.exe)) { throw "Run install.ps1 first." }
.\.venv\Scripts\iras.exe
