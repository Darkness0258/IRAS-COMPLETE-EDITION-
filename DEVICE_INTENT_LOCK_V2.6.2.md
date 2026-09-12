# IRAS v2.6.2 — Device Intent Lock

This fixes a remote-control bug where a simple request such as:

```text
open Chrome
```

could cause IRAS to open both Chrome and VS Code.

## Cause

The v2.6 smart-tool router exposed every device-control tool whenever any
device-related phrase was detected. For `open chrome`, the model could see:

```text
device_open_app
device_open_project
device_run_tests
device_capture_screen
device_read_text
...
```

Recent conversation context could therefore influence it into selecting an
unrequested action such as opening VS Code.

## Fix

v2.6.2 applies two layers.

### 1. Intent-specific tool exposure

Examples:

```text
open Chrome
→ device_open_app only

open my project in VS Code
→ device_open_project only

run the tests on my PC
→ device_run_tests only

check git status on my PC
→ device_git_status only
```

### 2. App-target guard

For:

```text
open Chrome
```

the current-turn allowed app target becomes:

```text
chrome
```

If the model tries to call:

```text
device_open_app(app="vscode")
```

the call is blocked before it reaches the Windows PC.

If the user explicitly says:

```text
open Chrome and VS Code
```

both targets remain allowed.

This prevents old conversation context from causing extra application launches.

## Version

```text
IRAS / Windows: 2.6.2
Android: 2.6.2
Android versionCode: 20602
```
