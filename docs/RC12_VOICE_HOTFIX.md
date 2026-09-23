# IRAS RC12 Cross-Platform Voice Hotfix

This hotfix repairs the production voice paths without changing Remote Protocol 1.

## Windows PC
- `iras-cloud-client` now has local `/voice`, `/voice test`, `/voice test edge`,
  `/voice test windows`, and `/listen` commands.
- Cloud replies can be spoken through the existing Edge TTS -> Windows SAPI fallback.
- The cloud client advertises the `voice` capability.
- Local microphone capture now checks whether 16 kHz is supported and falls back
  to the selected device's native sample rate when necessary.
- `python -m iras.cli --voice-test ...` now executes correctly; the missing module
  entry-point guard previously made voice-doctor TTS checks appear blank.
- The desktop shell now honors the configured `IRAS_VOICE_PROFILE`.

## Android
- Hands-free startup now owns the RECORD_AUDIO permission flow instead of silently
  remaining enabled without permission.
- Permission denial updates persisted state/UI instead of leaving a false "On" state.
- Fatal recognizer errors stop retry loops; transient failures use bounded retry delays.
- If `/v1/tts` fails, Android falls back to native TextToSpeech.
- Cloud TTS error bodies are surfaced in the local fallback reason.
- Android cloud-client registration now reports v5.0.0-rc12.
- Notification and microphone permission prompts are sequenced to avoid startup races.
- Playback stops active speech recognition and restarts hands-free capture after
  cloud/native speech finishes or fails, reducing self-echo and missed wake words.
- Android 11+ package visibility now declares both the recognition service and TTS
  service required by the platform APIs.
- Speech language and voice mood settings are now actually persisted by the Settings dialog.

## Web / Render
- Web playback falls back to browser SpeechSynthesis when cloud MP3 generation/playback fails.
- Browser TTS is cancelled on interruption so barge-in remains truthful.
- Hands-free persistence preserves the existing server/language/mood configuration
  instead of replacing the whole saved configuration object.
- `/v1/tts` retries one stable female English voice if the selected locale voice fails.
- `/v1/voice/health` exposes authenticated backend/configuration diagnostics.
- HTTP 502 TTS failures include bounded upstream error detail for diagnosis.

## Compatibility
- Package version remains `5.0.0-rc12`.
- Remote Protocol remains `1`.
- Permission, authentication, UAC, emergency-stop and Master/Remote boundaries are unchanged.

## Diagnostics

Run `./voice-doctor.ps1` from PowerShell. Add `-TestMicrophone` for a real
microphone + Whisper capture test and `-PlayRenderAudio` to play the Render MP3.
