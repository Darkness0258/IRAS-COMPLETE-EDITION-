# IRAS v2.7.5 — Spotify Reliable Control

The v2.7.4 cloud routing is working. The remaining bug is on Windows: the
controller called `SetForegroundWindow()` but never checked whether Windows
actually gave Spotify keyboard focus. Windows can reject that request from a
background polling thread, so IRAS could report success while Ctrl+K/text/Enter
went to another window.

v2.7.5 adds verified foreground focus, a Spotify URI search fallback, fresh
Ctrl+K search input, and explicit diagnostics.

Expected Windows log after a successful request:

```text
[IRAS SPOTIFY] query='Majboor song' deep_link=True foreground=True
```

If focus cannot be verified, the command now fails instead of pretending it was
sent to Spotify.

It also accepts the narrow speech-recognition form `yah majbur song` as a music
request.
