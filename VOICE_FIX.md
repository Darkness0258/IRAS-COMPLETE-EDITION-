# IRAS 1.1.2 Voice Fix

Changes:
- Spoken replies default to on.
- Edge TTS/MPV errors are no longer suppressed.
- Windows SAPI is a real checked fallback backend.
- `voice test` and `iras --voice-test` report the working backend or exact failure.
- `listen`, `/listen`, `mic`, and `/mic` provide one-shot microphone input.
- TTS text is sent safely to PowerShell over stdin instead of interpolated into a command.

For microphone input install:

```powershell
pip install -e ".[voice,dev]"
```

For reply-only TTS, the normal install is enough.
