# IRAS v2.7.0 — Desktop Interaction Engine

v2.6 could launch approved applications but could not operate inside them.

v2.7 adds a bounded Windows UI interaction tool:

```text
device_interact_app
```

Approved apps:

```text
Chrome
Spotify
VS Code
Notepad
File Explorer
```

Supported actions:

```text
wait
type
press
hotkey
click
double_click
scroll
```

Examples:

```text
IRAS, open Chrome and search YouTube.
Type hello world in Notepad.
Search OpenAI in Chrome.
Press F5 in VS Code.
Scroll down in Chrome.
```

A Chrome search is executed as a bounded sequence such as:

```text
focus/launch Chrome
Ctrl+L
type the query
Enter
```

Safety restrictions:

- maximum 15 actions per call;
- maximum 4000 total typed characters;
- limited wait time;
- Windows-key shortcuts blocked;
- Ctrl+Alt+Delete blocked;
- Alt+F4 blocked;
- approved app targets only;
- current-turn app-intent guard stays active;
- no cmd, PowerShell, arbitrary executable, or shell tool.

Mouse clicking is coordinate-based. Until screenshot vision is added, keyboard
interactions are more reliable.

Version:

```text
IRAS / Windows: 2.7.0
Android: 2.7.0
Android versionCode: 20700
```
