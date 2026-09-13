# IRAS v3.4.5 — Spotify Quick Search Reliability

Real-device testing showed Spotify's modern Quick Search overlay after IRAS typed a requested track. The overlay itself exposes the keyboard contract:

- Enter → Open
- Shift+Enter → Play

IRAS v3.4.4 pressed Enter and then searched the page for a large bright-green "Top Result Play" button. That button is not present in the active Quick Search overlay, so a valid request could fail even though the correct result was already highlighted.

## v3.4.5 behavior

`device_spotify_play` now focuses Spotify, opens Quick Search with Ctrl+K, types the requested query, waits for results, and sends Spotify's own Shift+Enter Play shortcut for the highlighted result.

The historical green-button detector remains only as a compatibility fallback if the Quick Search keyboard action itself cannot be injected. The query playback path still does not use a generic MEDIA_PLAY command, preserving the existing safety rule against resuming an unrelated previous track.

Direct device errors also collapse repeated exception prefixes, so users no longer see messages such as `RuntimeError: RuntimeError: ...`.

This is an action-reliability hotfix. Strong semantic outcome verification remains planned for v3.5.
