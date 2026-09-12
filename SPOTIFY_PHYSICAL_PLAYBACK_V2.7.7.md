# IRAS v2.7.7 — Spotify Physical Playback

v2.7.6 proved that search is working, but playback stayed paused.

The diagnostic showed a Play-button target coordinate while the detector
returned zero green pixels. The supplied screenshot shows the visible Spotify
green Play button at essentially the same physical-pixel location. That points
to Windows DPI coordinate virtualization between screenshot/window coordinates
and `SetCursorPos`.

v2.7.7 fixes the final playback stage:

- gets physical window bounds with
  `DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)`;
- moves the pointer with `SetPhysicalCursorPos`;
- verifies the actual pointer location using `GetPhysicalCursorPos`;
- clicks only after Spotify is foreground;
- sends explicit Windows `APPCOMMAND_MEDIA_PLAY` after the click.

`APPCOMMAND_MEDIA_PLAY` is PLAY, not PLAY_PAUSE, so it is safe as a second
start signal and will not pause a track that the click already started.

Expected local log:

```text
[IRAS SPOTIFY] ... cursor_actual=(x,y) media_play=True
```

Version:

```text
IRAS / Windows: 2.7.7
Android: 2.7.7
Android versionCode: 20707
```
