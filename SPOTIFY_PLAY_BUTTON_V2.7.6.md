# IRAS v2.7.6 — Spotify Top-Result Play Button

v2.7.5 proved that Spotify launches, searches, and receives foreground focus.
The remaining screenshot shows the top result with its large green Play button
still visible, which means the keyboard sequence committed/navigated the search
but did not start playback in this Spotify build.

v2.7.6 no longer assumes ArrowDown + Enter means Play. After search results are
visible, IRAS captures the Spotify window, detects Spotify-green pixels in the
upper-center Top Result area, and clicks the actual green Play button.

If visual detection cannot find the button, IRAS falls back to a window-relative
Top Result play position rather than a fixed screen coordinate.

Expected diagnostic:

```text
[IRAS SPOTIFY] query='Majboor song' deep_link=True foreground=True play_click=(...) green_detected=True green_pixels=...
```

Version:

```text
IRAS / Windows: 2.7.6
Android: 2.7.6
Android versionCode: 20706
```
