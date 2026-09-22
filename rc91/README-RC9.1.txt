IRAS RC9.1 — FEMALE IDENTITY + ROMAN URDU DEFAULT
=================================================

This package is cumulative. If RC9 is not installed, the PowerShell installer
first applies the bundled RC9 package (which itself contains RC8 -> RC7 -> RC6),
then applies this RC9.1 identity/default overlay.

DEFAULT IDENTITY
- IRAS voice identity is always female.
- Roman Urdu (Latin script) is the default conversation language.
- Default spoken locale is Urdu (Pakistan): ur-PK.
- Default Urdu neural voice: ur-PK-UzmaNeural.
- Calm remains the default delivery mood.
- Male voice requests from older clients are accepted for compatibility but ignored.
- Strong/explicit language switches still work; multilingual support is preserved.

DEFAULT ENVIRONMENT
IRAS_LANGUAGE=roman-urdu
IRAS_VOICE_MOOD=calm
IRAS_VOICE_GENDER=female
IRAS_WHISPER_MODEL=base

INSTALL
  cd <extracted-folder>
  .\apply-iras-rc91.ps1 -Repo "D:\Projects\IRAS-complete" -Test

FULL VALIDATION
  cd D:\Projects\IRAS-complete
  .\.venv\Scripts\Activate.ps1
  .\run-v500-validation.ps1

ROLLBACK ONLY RC9.1
  .\restore-iras-rc91.ps1 -Repo "D:\Projects\IRAS-complete"

Remote protocol remains 1. No permission, Master Control, UAC, audit, Remote,
or Emergency Stop boundary is weakened.
