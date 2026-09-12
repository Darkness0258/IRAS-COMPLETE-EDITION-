# IRAS v2.7.4 — Deterministic Media Router

High-confidence media commands execute through the permissioned device registry
instead of being left to ordinary chat routing.

Examples:

```text
play Majboor song
→ device_spotify_play(query="Majboor song")

open Spotify and play Majboor
→ device_spotify_play(query="Majboor")

play the song
→ device_media_control(command="play")

pause the song
→ device_media_control(command="pause")
```

The last device action is retained so `try again`, `retry`, and `do it again`
can repeat it. A non-music phrase such as `play GTA 5` is not hijacked as a
Spotify request.
