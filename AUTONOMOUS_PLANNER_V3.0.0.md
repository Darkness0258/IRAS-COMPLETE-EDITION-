# IRAS v3.0.0 — Bounded Autonomous Device Planner

## Why v2.9 commands felt rigid

v2.9 successfully added installed-app auto-detection, but the cloud agent still
selected device tools mainly through hard-coded phrases. A new sentence such as:

```text
open Discord and send hello to Hamza
search Hamza in Discord
open Edge and then search for OpenAI
click settings in Telegram
play GTA 5
```

could miss the deterministic regex route. When that happened, `_smart_tool_names`
returned no device tools and the language model could only chat about the task
instead of carrying it out.

## v3 architecture

v3 keeps deterministic fast paths for well-known commands, but adds a bounded
model-led planner as a fallback.

```text
user request
  ↓
known deterministic command? ── yes ──> execute fast path
  ↓ no
looks like a real device task?
  ↓ yes
expose only bounded device tools
  ↓
model privately plans next safe action
  ↓
execute real tool
  ↓
feed actual result/error back to model
  ↓
model adapts / calls next tool
  ↓
finish or explain missing capability truthfully
```

The planner can inspect installed apps, open/focus/control them, interact with
keyboard/mouse actions, operate Spotify/media, open URLs/projects, inspect files,
run bounded project tests, read Git status, and capture the screen.

## Safety remains intact

This is not unrestricted PC execution. Planner mode deliberately does **not**
expose:

```text
run_shell
launch_app
kill_process
arbitrary subprocess
registry/admin consoles
permission bypasses
```

All selected device tools still execute through `ToolRegistry.execute()`, so
permissions and audit logs stay in force. App launching also retains the v2.9
shell/admin denylist.

## Current-turn app scope

The planner now extracts app names from the current user turn. For example:

```text
open Discord and send hello to Hamza
```

scopes GUI actions to Discord. A model call that tries to open Slack from old
conversation context is blocked.

## Better Spotify search language

The following now route directly:

```text
search Heeriye in Spotify
search Spotify Heeriye
find Heeriye on Spotify
look for Heeriye in Spotify
```

After a Spotify action, short follow-ups also work:

```text
search another song
find Atif Aslam
look up Pasoori
```

## What "think for herself" means here

IRAS can now choose and sequence tools dynamically rather than needing a regex
for every exact sentence. She can recover from safe tool errors and try another
bounded approach. Internal chain-of-thought is not displayed or logged; only
real tool calls/results are audited.

It still cannot magically operate an arbitrary unknown visual UI when no
available tool exposes the needed control or screen understanding. In that case
v3 must state what capability is missing rather than guess coordinates or claim
success.

## Installation

Extract over the existing v2.9.0 repository and run:

```powershell
cd D:\Projects\IRAS-complete
.\apply-autonomous-planner-v3.0.0.ps1
```

The installer runs dedicated planner regressions, then the complete historical
pytest suite, then a command-routing matrix before it commits or pushes.
