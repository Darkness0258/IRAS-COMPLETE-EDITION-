# IRAS v2.7.2 — Action Truth + Spotify Control

The Render log exposed the actual bug:

```text
[IRAS LATENCY] ... tools=1 rounds=0 ...
```

A device tool was available, but `rounds=0` means the model did not actually call
a tool. It answered as if the action had happened.

That is why IRAS could say:

```text
Spotify's open and Majboor is playing
```

even when playback did not start.

v2.7.2 fixes three things.

## Action truthfulness

For a smart-routed tool turn, IRAS no longer accepts a text-only success response.
It retries once with an explicit requirement to call the selected tool. If the
model still refuses to call a tool, IRAS says it could not execute the action
instead of pretending it succeeded.

## Dedicated Spotify play

`device_spotify_play` focuses/opens Spotify and performs the documented Windows
quick-search sequence:

```text
Ctrl+K
type query
Down
Enter
```

Spotify documents Ctrl+K as Quick Search. Spotify community moderators also
document that selecting a result and pressing Enter starts playback.

The tool reports that the command was sent; it does not falsely claim that audio
playback was independently verified.

## Media follow-ups

`device_media_control` adds bounded Windows media keys for:

```text
play / pause / resume
next
previous
stop
mute
volume up/down
```

So a follow-up like `play the song` now becomes a real PC media command instead
of ordinary chat.

Version:

```text
IRAS / Windows: 2.7.2
Android: 2.7.2
Android versionCode: 20702
```
