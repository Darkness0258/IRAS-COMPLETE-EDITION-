# IRAS v2.9.0 — Auto App Control Engine

v2.9.0 expands IRAS from a small hard-coded application allowlist into a
permissioned auto-detection layer for normal Windows GUI applications.

## What it fixes

### Media stop / pause / resume

The media controller now auto-detects the most likely active media app.

For `stop`, IRAS sends:

1. Windows `APPCOMMAND_MEDIA_STOP` to the detected media window;
2. explicit `APPCOMMAND_MEDIA_PAUSE` as an idempotent fallback for players such
   as Spotify that do not expose a true Stop state;
3. the global Windows Media Stop key as a final safe stop signal.

`play` and `pause` remain distinct commands instead of blindly toggling state.

Examples:

```text
pause
resume
stop
next song
previous song
pause music in VLC
stop music in Spotify
```

## Installed-app auto detection

IRAS builds a local app catalog from:

- the Windows Start Apps catalog (`Get-StartApps`) using a fixed internal
  discovery command with no user text interpolated into PowerShell;
- Windows `App Paths` registry entries.

It can therefore resolve common installed apps without adding them to source
code one-by-one, for example:

```text
open Discord
open VLC
open Microsoft Edge
open WhatsApp
open Telegram
open Steam
open Calculator
```

Matching supports exact names, aliases, and conservative fuzzy matching.
Ambiguous matches fail instead of silently opening the wrong app.

## App controls

For any detected normal GUI application with a visible window:

```text
focus Discord
minimize Telegram
maximize VLC
restore Chrome
close WhatsApp
```

Closing uses `WM_CLOSE`, not force-killing the process.

## Generic interaction

The existing bounded UI-input engine now works with auto-detected app names:

```text
type hello there in Discord
press enter in Notepad
scroll down in Telegram
search OpenAI in Edge
```

All previous input limits remain: no Windows-key shortcuts, no Ctrl+Alt+Delete,
no Alt+F4, bounded actions, bounded text and bounded waits.

## App discovery

```text
what apps are installed
what apps are running
find app Discord
```

uses `device_detect_apps` and returns installed and visible/running apps.

## Safety boundary

Auto detection does **not** mean unrestricted command execution. IRAS continues
to block command shells and administrative consoles such as Command Prompt,
PowerShell, Windows Terminal, Registry Editor, WSL and similar high-risk launch
targets. The remote bridge still has no arbitrary shell action.

## Scope

"All apps" means normal GUI apps discoverable through Windows Start Apps or App
Paths and/or apps with a visible top-level window. IRAS can generically launch,
focus, minimize, maximize, restore, gracefully close, type, press bounded keys,
scroll and use known media transport controls. App-specific workflows that have
no standard shortcut or media interface still require explicit UI actions or a
future visual interaction loop.

## Version

```text
Python / Windows: 2.9.0
Android: 2.9.0
Android versionCode: 20900
```
