# IRAS Web Hands-Free Hotfix v2.5.1

This hotfix fixes the browser case where Hands-free shows as enabled but Chrome
does not reliably finalize a short wake-word utterance such as "IRAS".

Changes:

- explicitly verifies microphone permission/device access with getUserMedia;
- uses short recognition sessions that auto-restart instead of Chrome's flaky
  long-running `continuous=true` mode;
- accepts interim wake-word detection;
- shows live diagnostic states:
  - Mic active
  - I hear you
  - Processing what I heard
  - No speech detected
  - audio-capture failure
  - network failure
- automatically restarts recognition after normal/no-speech endings;
- pauses recognition while the tab is hidden and resumes when visible;
- keeps the manual Mic button as a diagnostic fallback.

After Render redeploys, hard-refresh Chrome with Ctrl+Shift+R.
