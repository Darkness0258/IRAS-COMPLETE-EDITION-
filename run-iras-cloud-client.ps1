$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .\.venv\Scripts\python.exe)) {
    throw "IRAS virtual environment is missing. Run .\\install.ps1 first."
}
& .\.venv\Scripts\python.exe -m iras.cloud_client @args
exit $LASTEXITCODE
