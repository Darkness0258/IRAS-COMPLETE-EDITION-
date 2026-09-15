# Build APK and EXE

The repository contains two GitHub Actions workflows:

- `.github/workflows/build-android-apk.yml`
- `.github/workflows/build-windows-exe.yml`

## Why builds are done in GitHub Actions

A Windows EXE should be built on Windows, and an Android APK needs the Android SDK. GitHub-hosted Windows/Linux runners provide the correct build environments.

## Run builds

Push the repository to GitHub, then:

1. Open **Actions**.
2. Select **Build Windows EXE** -> **Run workflow**.
3. Select **Build Android APK** -> **Run workflow**.
4. Open each finished run and download its artifact.

Artifacts:
- `IRAS-Windows-EXE` -> `IRAS.exe`
- `IRAS-Android-APK` -> `app-debug.apk`

The APK is a debug build intended for your own devices/testing. A Play Store release would require signing and a release key.

## Client setup

On first launch both clients ask for:
- server URL, for example `https://iras-yourname.koyeb.app`
- IRAS access token, matching `IRAS_API_TOKEN` on the backend

The OpenRouter key remains on the server.
