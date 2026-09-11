# IRAS Secure Device Control Bridge v2.6.0

IRAS can now control a paired Windows PC from the existing Web and Android
chat clients through the Render cloud brain.

## Architecture

```text
Android / Web
      |
      v
IRAS Cloud (Render)
      |
      | encrypted HTTPS command queue
      v
Windows IRAS EXE
      |
      +-- approved local actions
```

The Windows computer never opens an inbound port. It maintains an outbound
HTTPS long-poll to the existing IRAS Cloud server.

## Automatic secure pairing

The Windows EXE already knows the user's IRAS server URL and API token.
On first start, v2.6 generates a stable device ID, pairs through the authenticated
cloud endpoint, receives a random device secret, and stores it locally. The cloud
stores only the SHA-256 hash of that secret.

## Available remote actions

```text
device_system_info
device_open_app
device_open_url
device_open_project
device_list_files
device_read_text
device_git_status
device_run_tests
device_capture_screen
```

There is deliberately NO arbitrary `device_shell`, remote PowerShell, or generic
command-execution tool in this release.

### App launching

Remote app launch is restricted to approved aliases:

```text
VS Code
Chrome
Spotify
Notepad
Explorer
```

### Files

Remote file reads are restricted to allowed local roots. Defaults include the
Windows user's home directory and, when present, `D:\Projects` and
`C:\workstation\Projects`.

Additional roots can be configured before starting the EXE:

```powershell
$env:IRAS_BRIDGE_ROOTS="D:\Projects;E:\Work"
```

### Tests

`device_run_tests` does not accept a command string. IRAS selects only a bounded
runner based on the target project: `python -m pytest -q`, `npm test`, or
`pnpm test`.

## Example commands from Android or Web

```text
IRAS, open VS Code on my PC.
Open D:\Projects\IRAS-complete in VS Code on my computer.
Check git status in D:\Projects\IRAS-complete on my PC.
Run the tests in D:\Projects\IRAS-complete on my computer.
List the files in D:\Projects on my PC.
Take a screenshot on my PC.
```

## Screenshot limitation

The screenshot action captures the desktop to a local IRAS screenshot file and
returns its path, dimensions, and file size. Automatic screenshot upload and
vision analysis are not included yet.

## Requirement

The Windows IRAS EXE must be running for remote actions to work. An always-on
Windows background service is a later step.

## Version

```text
IRAS / Windows: 2.6.0
Android: 2.6.0
Android versionCode: 20600
```
