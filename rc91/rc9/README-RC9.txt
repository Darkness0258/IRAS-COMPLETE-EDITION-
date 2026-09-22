IRAS RC9 — MULTILINGUAL VOICE & LANGUAGE INTELLIGENCE
======================================================

This is a cumulative update package. If RC8 is missing, apply-iras-rc9.ps1
will apply the bundled RC8 package first (which itself bundles RC7 and RC6).

MAIN FEATURES
- 23-language voice catalog with matched female/male neural voices.
- Urdu Pakistan first-class voices: UzmaNeural + AsadNeural.
- Default calm delivery; warm, bright, neutral modes available.
- Automatic dominant-language TTS routing.
- Conservative Roman Urdu detection.
- Multilingual Faster-Whisper default (`base`, not English-only `base.en`).
- Whisper detected-language/probability metadata retained locally.
- Existing English voice profiles remain usable for English.
- Cloud voice catalog + voice resolve API endpoints.
- Web language/mood/gender settings and language-aware browser STT.
- Android language/mood/gender settings and no hardcoded en-US recognition.
- IRAS persona mirrors the user's current language naturally.

INSTALL
1. Extract this ZIP.
2. In PowerShell:

   cd <extracted-folder>
   .\apply-iras-rc9.ps1 -Repo "D:\Projects\IRAS-complete" -Test

3. Then run the full project validation:

   cd D:\Projects\IRAS-complete
   .\.venv\Scripts\Activate.ps1
   .\run-v500-validation.ps1

DEFAULTS
IRAS_LANGUAGE=auto
IRAS_VOICE_MOOD=calm
IRAS_VOICE_GENDER=female
IRAS_WHISPER_MODEL=base

Useful examples:
IRAS_LANGUAGE=ur-PK   # Force Urdu Pakistan
IRAS_LANGUAGE=auto    # Auto route per text / Whisper detection
IRAS_VOICE_MOOD=warm
IRAS_VOICE_GENDER=male

ROLLBACK
.\restore-iras-rc9.ps1 -Repo "D:\Projects\IRAS-complete"

NOTES
- TTS remains Edge neural voice first with the existing Windows SAPI fallback.
- Voice quality is subjective. "Calm" is implemented as curated voice choice plus
  slightly slower/lower delivery, not as a claim about emotion.
- Remote protocol remains 1. RC9 does not widen tool permissions or bypass Master,
  Remote authorization, UAC, audit, or Emergency Stop.
