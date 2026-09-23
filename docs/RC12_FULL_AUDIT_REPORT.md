# IRAS v5.0 RC12 Full Source Audit Report

Audit date: 2026-09-23

## Scope

This audit used the uploaded RC12 project as the source of truth and inspected the complete distributable source tree, not only the voice modules. The final sanitized package contains 476 project files, including 359 Python files, the Android client, web/PWA client, PowerShell launch/validation scripts, deployment configuration, tests, and release documentation.

The original upload also contained local-only material (`.env`, `.venv`, `.git`, runtime `data/`, runtime `logs/`, caches, and standalone hotfix installer files). Those are intentionally excluded from the final source ZIP. `.env.example` remains available as the configuration template.

## Verified release identity

- IRAS version: `5.0.0-rc12`
- Feature families: 37
- Model-facing v5 tools: 206
- Remote Protocol: 1
- Android `versionCode`: 50012
- Android `versionName`: `5.0.0-rc12`
- Web and Android cloud-client registration: `5.0.0-rc12`

## Voice defects fixed

### Windows / PC

- Added real microphone and spoken-response support to `iras-cloud-client`; it was previously text-only.
- Added `/voice`, `/voice on`, `/voice off`, `/voice test`, `/voice test edge`, `/voice test windows`, `/listen`, and `/mic` behavior to the cloud client.
- Fixed `python -m iras.cli ...` by restoring the missing module entry point, which was why the previous voice doctor showed blank Windows/Edge TTS sections.
- Microphone capture now checks whether the requested 16 kHz input format is supported and falls back to the selected device's native input sample rate when necessary.
- Desktop and Remote desktop now respect configured voice-reply settings; the desktop also respects the configured voice profile.
- Added `voice-doctor.ps1` for microphone inventory, optional live Whisper capture, Windows SAPI, Edge-TTS/MPV, Render voice health, Render MP3 generation, and optional playback.

### Android

- Fixed first-launch hands-free microphone permission flow.
- Sequenced notification and microphone permission prompts to avoid a startup permission race on modern Android.
- Added required Android 11+ package-visibility queries for the system speech-recognition service and TTS service.
- Added native Android `TextToSpeech` fallback when cloud `/v1/tts` fails.
- Added cloud TTS error-body diagnostics instead of reducing every failure to a generic message.
- Improved fatal/transient `SpeechRecognizer` error handling to avoid misleading or aggressive retry loops.
- Fixed settings persistence for speech language and voice mood.
- Stops recognition during speech playback to reduce self-echo, then restarts hands-free capture after cloud or native speech completion/failure.
- Corrected stale RC4 cloud-client registration identity to RC12.
- Ensures `SpeechRecognizer.destroy()` and `TextToSpeech.shutdown()` are called during teardown.

### Web / Render

- Added browser `SpeechSynthesis` fallback if Render MP3 generation or playback fails.
- Cancels browser speech on interruption/barge-in.
- Fixed hands-free preference persistence so toggling hands-free no longer deletes saved language/mood settings.
- Corrected stale RC4 web cloud-client registration identity to RC12.
- `/v1/tts` now retries a stable female voice if the selected locale-specific Edge voice fails.
- Added authenticated `/v1/voice/health` configuration diagnostics.
- Cloud TTS HTTP 502 responses now include bounded backend diagnostic detail.

## Whole-tree validation

The final source passed the following automated checks on the audit host:

- Full pytest suite: **951 passed, 0 failed**.
- RC12 integrated validator: **PASS**.
- Validated feature families: **37**.
- Model-facing v5 tool count: **206**.
- Remote Protocol: **1**.
- Python syntax/AST parse: all 359 Python files passed.
- JSON parse: passed.
- TOML parse: passed.
- YAML parse: passed.
- XML parse: passed.
- Web inline JavaScript: `node --check` passed.
- Service worker JavaScript: `node --check` passed.
- Android Java structural delimiter/string/comment scan: passed.
- Merge-conflict marker scan: none found.
- UTF-8 BOM scan on project text files: none found.
- Credential-pattern scan outside local `.env`: no obvious committed credential tokens found.
- `git diff --check`: passed.
- Clean-tree validator: designed to pass after test/cache cleanup and does not require a local `.env`.

## Research-backed compatibility changes

Android's official API documentation requires apps targeting Android 11+ to expose package visibility for both speech-recognition services and TTS engines through manifest `<queries>` declarations. RC12 now declares both. The web fallback also reflects the Web Speech API compatibility reality: browser `SpeechRecognition` has limited cross-browser availability, while `SpeechSynthesis` is widely available. Therefore IRAS retains explicit recognition capability checks and uses local speech synthesis only as a playback fallback, not as a false promise of universal browser speech recognition.

`edge-tts` 7.2.8 remains the current PyPI release as of the audit date, matching IRAS's `edge-tts>=7.2.8` dependency floor.

## What cannot be proven inside a source-only audit

- Physical microphone quality, Windows privacy permissions, actual speaker volume/device routing, and audible playback must be tested on the target PC. Use `voice-doctor.ps1 -TestMicrophone -PlayRenderAudio`.
- Android source was structurally validated, but a real APK build/reinstall still requires an Android SDK/Gradle environment. The phone must receive a newly built APK for these Android changes to take effect.
- The new Render `/v1/voice/health` route will return 404 until this fixed source is pushed and Render finishes its automatic deployment. The existing deployed `/v1/tts` was already confirmed to return a valid MP3 from the user's Windows voice doctor.
- No source audit can guarantee that every future provider, OS, browser, driver, network, or hardware failure is impossible. The changes above add fallbacks and diagnostics so such failures are observable instead of silently appearing as “voice not working.”
