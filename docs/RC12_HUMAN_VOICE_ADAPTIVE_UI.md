# IRAS v5.0.0 RC12 — Human Voice + Adaptive UI

## Voice identity

IRAS now defaults to the `iras_human` voice profile.

Primary English voice:

- `en-US-AvaMultilingualNeural`

All-female fallback chain:

1. `en-US-EmmaMultilingualNeural`
2. `en-US-PhoebeMultilingualNeural`
3. `en-US-JennyNeural`

The profile is deliberately a voice identity/preset, not a clone of a real person. It keeps IRAS feminine, warm, natural, concise, and consistent while preserving the existing multilingual routing rules.

Roman Urdu and native-language routing remain independent. Roman Urdu keeps the configured South-Asian Latin voice (`IRAS_ROMAN_URDU_VOICE`, currently `en-IN-NeerjaNeural`) and native Urdu keeps `ur-PK-UzmaNeural` unless explicitly reconfigured.

## Runtime customization

```env
IRAS_VOICE_PROFILE=iras_human
IRAS_HUMAN_VOICE=en-US-AvaMultilingualNeural
IRAS_HUMAN_VOICE_FALLBACKS=en-US-EmmaMultilingualNeural,en-US-PhoebeMultilingualNeural,en-US-JennyNeural
IRAS_VOICE_MOOD=warm
```

`IRAS_HUMAN_VOICE` can be changed to another compatible female Edge/Azure neural voice without editing source code.

## Cloud API

`POST /v1/tts` and `POST /v1/voice/resolve` accept:

```json
{
  "text": "Hello",
  "language": "roman-urdu",
  "mood": "warm",
  "voice_gender": "female",
  "voice_profile": "iras_human"
}
```

`GET /v1/voice/profiles` exposes the active profile catalog and fallback metadata.

## Adaptive UI

### Web / PWA

- Live IRAS voice presence indicator with idle/listening/thinking/speaking/error states.
- Human voice selector in Settings.
- Responsive mobile bottom dock with safe-area handling.
- Larger glass surfaces, stronger focus states, adaptive ambient motion, and compact phone layout.
- Browser TTS fallback now prefers feminine voices when the cloud voice is unavailable.

### Android

- Dedicated IRAS Human voice presence card.
- Live visual state updates driven by the existing status stream.
- Human voice profile selection is persisted and sent with each cloud TTS request.
- Warmer local TTS fallback tuning for the human profile.
- Improved elevation and hierarchy around the composer and voice surface.

### Windows desktop

- Human voice status capsule in the command center header.
- Voice identity shown in the runtime card.
- One-click profile cycling across Human, Soft, Cool, Energetic, and Neutral profiles.
- Speaking/listening/thinking/error state reflected in the voice capsule.

## Compatibility

- Remote Protocol remains `1`.
- Existing Roman Urdu / Urdu / English multilingual routing contracts remain intact.
- Existing voice profiles remain available.
