# IRAS v2.9.0 — Full Auto-App Regression Fix

This continuation fixes the issues found by the first real Windows v2.9.0 run.

## Fixed test regressions

- `open chrome and search youtube` again routes to `device_interact_app`.
- `open my project in VS Code on my PC` remains owned by `device_open_project`.
- `play video on YouTube` is not misread as a media-resume command.
- the desktop interaction contract now expects `UniversalWindowsController`.
- PowerShell/cmd remain blocked even though app launching is now dynamic.

## Fixed runtime media problems

The original auto-media selector treated every Chrome window as a media app. A
normal `IRAS Build Watch - Google Chrome` window could therefore receive Stop.
Browsers are now media candidates only when their title contains a media target
such as YouTube/Netflix/etc. Dedicated players such as Spotify and VLC are still
recognized by process name.

Generic media control never targets an arbitrary foreground window anymore.
When no safe media window is identified it uses bounded Windows media keys.

For an explicit app that is installed but not running:

- `pause` and `stop` are safe no-ops rather than exceptions;
- `play`, `next`, and `previous` return a truthful not-running error instead of
  controlling a different application.

For a running target, `stop` sends both explicit STOP and idempotent PAUSE to
that target. This handles Spotify/VLC implementations that do not honor STOP.

## Safer automatic app discovery

Shell-capable and administrative command hosts are filtered from dynamic launch
resolution, including PowerShell variants, command prompts, Windows Terminal,
Anaconda PowerShell Prompt, WSL, bash, regedit, mmc, and Python launch targets.
The denylist is enforced inside `launch_app`, before PATH or App-Paths lookup.

No arbitrary remote shell was added.
