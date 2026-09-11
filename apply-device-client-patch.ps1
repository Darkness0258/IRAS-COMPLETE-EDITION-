$ErrorActionPreference = "Stop"

Write-Host "Applying IRAS device-client v2.1.1 patch..."

if (-not (Test-Path ".git")) {
    throw "Run this script from the root of your IRAS-COMPLETE-EDITION- Git repository."
}

git add `
  clients/android/app/src/main/java/com/darkness/iras/MainActivity.java `
  clients/android/app/build.gradle `
  src/iras/remote_desktop.py `
  .github/workflows/build-android-apk.yml `
  .github/workflows/build-windows-exe.yml `
  DEVICE_CLIENTS_V2.1.1.md

git commit -m "finish Android and Windows cloud clients"
git push origin main

Write-Host ""
Write-Host "Pushed."
Write-Host "GitHub Actions should now build:"
Write-Host "  - IRAS-Android-APK"
Write-Host "  - IRAS-Windows-EXE"
