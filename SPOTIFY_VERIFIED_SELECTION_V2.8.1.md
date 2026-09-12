# IRAS v2.8.1 — Spotify Verified Selection

The v2.8.0 screenshot/log isolated the remaining wrong-track bug.

Spotify correctly searched for `Heeriye Jasleen Royal`, but `dilrubaa`
continued playing. The old log showed:

```text
green_detected=False
green_pixels=0
media_play=True
```

IRAS had not detected the requested result's green Play button. It then used a
guessed coordinate and generic MEDIA_PLAY, which resumed the old track.

v2.8.1 removes that behavior.

```text
search
→ wait up to 8 seconds for Spotify results
→ detect connected Spotify-green components
→ reject tiny check/status icons
→ choose the large Play-button component
→ verify Spotify foreground
→ click the detected result
→ never send generic MEDIA_PLAY as a fallback
```

If the result button cannot be detected, IRAS returns an error rather than
playing the wrong track.
