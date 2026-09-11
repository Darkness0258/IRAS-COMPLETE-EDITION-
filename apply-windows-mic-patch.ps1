$ErrorActionPreference = "Stop"

Write-Host "Applying IRAS Windows microphone patch v2.1.2..."

if (-not (Test-Path ".git")) {
    throw "Run this script from the root of your IRAS Git repository."
}

git add `
  src/iras/remote_desktop.py `
  .github/workflows/build-windows-exe.yml `
  WINDOWS_MIC_V2.1.2.md

git commit -m "add microphone to Windows IRAS client"
git push origin main

Write-Host ""
Write-Host "Pushed. GitHub Actions will rebuild IRAS-Windows-EXE."
