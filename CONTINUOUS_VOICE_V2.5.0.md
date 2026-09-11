# IRAS Continuous Conversation v2.5.0

IRAS can now stay in a hands-free conversation while the client is open.

## Wake word

Default wake word:

```text
IRAS
```

Examples:

```text
IRAS

IRAS open my project

Hey IRAS, what was I working on?
```

If the user says only `IRAS`, the conversation is armed briefly and the next
sentence does not need the wake word.

After IRAS answers, follow-up speech is accepted for roughly 20 seconds so the
conversation feels continuous.

## Windows EXE

- hands-free mode defaults on;
- local microphone VAD starts when speech begins and stops after silence;
- Faster-Whisper remains local;
- saying the wake word while IRAS speaks interrupts playback;
- echo suppression reduces IRAS hearing her own voice;
- streamed text is spoken sentence-by-sentence before the full answer ends;
- manual Mic remains as backup.

## Web

The `Hands-free` button enables continuous browser speech recognition.

Browsers control microphone permissions, so Chrome may require one user action
the first time hands-free mode is enabled.

Features:

- wake word;
- automatic recognition restart;
- follow-up conversation window;
- barge-in;
- echo suppression;
- sentence-by-sentence TTS while the answer streams;
- one-shot Mic remains available.

## Android

Continuous voice works while the IRAS app is in the foreground.

Features:

- wake word;
- automatic SpeechRecognizer restart;
- follow-up conversation window;
- barge-in;
- echo suppression;
- manual Mic remains available;
- IRAS voice plays after the streamed response completes.

A true always-on background hotword service is intentionally not enabled in
this release because Android requires foreground-service behavior and has
battery/privacy implications.

## Privacy

Windows VAD and Faster-Whisper run locally. Only transcribed text is sent to the
cloud backend.

Browser and Android recognition use the speech-recognition service supplied by
the platform/browser and may therefore use platform network services.
