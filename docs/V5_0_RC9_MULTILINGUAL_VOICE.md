# IRAS RC9 — Multilingual Voice & Language Intelligence

RC9 adds a language-aware speech layer on top of the cumulative RC6/RC7/RC8 system.

## What changes

- Local Faster-Whisper defaults to the multilingual `base` model instead of `base.en`.
- Whisper language detection metadata is retained on the `Listener` as `last_language` and `last_language_probability`.
- TTS automatically chooses a native neural voice from the detected response language.
- Urdu (Pakistan) is first-class: `ur-PK-UzmaNeural` by default and `ur-PK-AsadNeural` as the alternate.
- Roman Urdu receives a conservative marker-based fallback detector so common Latin-script Urdu can still use the Pakistani Urdu voice.
- Major script detection is dependency-free; Latin-language detection uses conservative markers/diacritics.
- Default voice delivery is `calm`: slightly slower and slightly lower pitch. `warm`, `bright`, and `neutral` modes are also available.
- The existing English/anime profile voice remains authoritative for English; language routing replaces it only when another language is selected/detected.
- Cloud `/v1/tts` now returns language/locale/voice headers and accepts optional `language`, `voice_gender`, and `mood` hints.
- Cloud exposes `/v1/voice/catalog` and `/v1/voice/resolve` for Web/Android/native clients.
- Web speech recognition gains a language selector and uses the chosen locale (or browser locale in Auto mode).
- Android speech recognition stops forcing `en-US`; it uses the configured/system locale, improving non-English recognition.
- The IRAS system prompt explicitly mirrors the user's language and supports natural mixed-language conversation while keeping code/commands unchanged.

## Environment controls

```env
IRAS_LANGUAGE=roman-urdu
IRAS_VOICE_MOOD=calm
IRAS_VOICE_GENDER=female
IRAS_WHISPER_MODEL=base
```

Examples for `IRAS_LANGUAGE`: `auto`, `ur`, `ur-PK`, `en`, `hi`, `ar`, `pa`, `fa`, `fr`, `es`, `de`, `it`, `pt`, `ru`, `uk`, `ja`, `ko`, `zh`, `bn`, `tr`, `vi`.

## Voice routing notes

The catalog uses standard Microsoft neural voice IDs. A voice can change upstream; RC9 therefore exposes the resolved voice and keeps a matched alternate voice. Edge TTS remains the primary online TTS backend, while existing Windows SAPI fallback is preserved.

RC9 does not claim biological emotion or sentience. “Calm/warm/bright” are audio delivery presets (rate/pitch/voice selection), not internal emotional states.

## RC9.1 identity defaults

- IRAS is always female across supported languages.
- Default conversation text is Roman Urdu (Latin script).
- Default speech locale is Urdu Pakistan (`ur-PK`) using `ur-PK-UzmaNeural`.
- Strong or explicit language switches remain supported.
