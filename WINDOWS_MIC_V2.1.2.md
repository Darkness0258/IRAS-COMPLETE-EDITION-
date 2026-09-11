# IRAS Windows Mic v2.1.2

Fixes the missing microphone control in the Windows EXE.

## New behavior

The Windows client now includes:

```text
[ input box ] [ Mic ] [ Send ] [ Voice ] [ Server ]
```

Pressing `Mic`:

1. records about 6 seconds from the default Windows microphone,
2. transcribes speech locally with Faster-Whisper,
3. inserts the transcription into the input box,
4. automatically sends it to the existing Render cloud backend,
5. receives the answer and speaks it with the configured IRAS voice.

## First microphone use

Faster-Whisper may download the configured Whisper model on first use.
The default IRAS configuration currently uses `base.en`.

This can make the first microphone activation slower. Later uses reuse the local model cache.

## Privacy

Microphone audio is transcribed locally by Faster-Whisper. The audio recording itself is not sent to Render. Only the resulting text is sent to the IRAS cloud chat endpoint.

## Build

The Windows GitHub Actions workflow now installs the `voice` extra and bundles:

- sounddevice
- soundfile
- faster-whisper
- ctranslate2
- Edge TTS

This makes the Windows artifact larger than the previous text-only EXE.
