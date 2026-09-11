# IRAS Device Clients v2.1.1

This patch finalizes the Android and Windows clients for the current IRAS cloud deployment.

## Android

Changes:

- defaults to `https://iras-cloud.onrender.com`
- uses `/v1/chat` for the shared cloud brain
- uses `/v1/tts` for the exact server-generated IRAS voice
- no longer uses Android's generic TextToSpeech voice
- microphone input remains available
- interrupting with the microphone stops current IRAS playback
- shared Supabase memory/personality works automatically because all chat goes through the same backend

The only value you must enter in the Android app is the same `IRAS_API_TOKEN` used by Render.

## Windows

Changes:

- defaults to `https://iras-cloud.onrender.com`
- fixes an existing `Speaker(Settings.load())` constructor bug
- now initializes the speaker with the configured provider, voice, and `anime_soft` profile correctly
- therefore Edge TTS uses the same `en-US-JennyNeural` IRAS profile instead of falling back immediately to Windows SAPI
- keeps Windows SAPI only as a fallback if Edge/MPV is unavailable

Your PC already has MPV, so the expected backend is `edge+mpv`.

## Builds

The included GitHub Actions workflows now build automatically when relevant files are pushed to `main`.

Artifacts:

- Android: `IRAS-Android-APK` -> `app-debug.apk`
- Windows: `IRAS-Windows-EXE` -> `IRAS.exe`

They can also still be started manually with **Actions -> Run workflow**.

## Shared memory test

On Web:

`Remember that my device-test phrase is Silver Eclipse 21.`

Then on Android or Windows:

`What is my device-test phrase?`

A correct answer confirms the clients are using the same Render backend and Supabase memory.
