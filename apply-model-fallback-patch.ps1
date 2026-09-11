$ErrorActionPreference = "Stop"

Write-Host "Applying IRAS automatic model fallback v2.1.3..."

if (-not (Test-Path ".git")) {
    throw "Run this script from the root of your IRAS Git repository."
}

git add `
  src/iras/providers/openrouter.py `
  tests/test_openrouter_fallback.py `
  MODEL_FALLBACK_V2.1.3.md

git commit -m "add automatic OpenRouter model fallback"
git push origin main

Write-Host ""
Write-Host "Pushed. Render auto-deploy should start."
Write-Host ""
Write-Host "After the deploy, set these Render variables:"
Write-Host "  IRAS_MODEL=nex-agi/nex-n2.5-mini:free"
Write-Host "  IRAS_FALLBACK_MODELS=openrouter/free"
