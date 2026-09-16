# IRAS v4 — Secure Worldwide Windows Access

IRAS v4 turns a Windows laptop into a **permissioned personal computer agent** that can be reached from IRAS Cloud anywhere the laptop has outbound Internet access. The design is intentionally not a stealth remote-access trojan: it creates no inbound listener on Windows, stores pairing secrets with Windows DPAPI, keeps a visible scheduled task, exposes an emergency stop, and requires both a cloud remote session and a locally armed laptop policy for privileged actions.

## Architecture

```text
browser / mobile browser / remote client
        |
        | HTTPS + IRAS_API_TOKEN
        v
     IRAS Cloud
        |
        | short-lived remote-session token
        v
 device command queue / audit
        ^
        | outbound HTTPS long-poll only
        |
 Windows laptop: iras-device
        |
        +-- local RemoteAccessPolicy (final permission gate)
        +-- EmergencyStop (controller-level kill switch)
        +-- DPAPI-protected pairing/API secrets
        +-- DeviceExecutor / verified UI primitives / semantic verifier
```

No router port-forwarding or inbound Windows firewall rule is required. GUI automation requires an interactive logged-in Windows desktop; IRAS does not bypass the Windows lock screen, UAC secure desktop, passwords, BitLocker, or OS authentication.

## One-time Windows setup

Install the package first:

```powershell
.\install-v4-windows.ps1 -AllFeatures -InstallBrowser
```

Deploy IRAS Cloud over HTTPS and configure a 32+ random-character `IRAS_API_TOKEN`. **Use the exact public URL shown by your cloud provider; example hostnames in this document are placeholders and will not work.** Before pairing a laptop, verify that `<your-real-url>/health` returns JSON containing `"ok": true`. The cloud deployment must run the same v4 code that contains the remote-device endpoints; an older stable backend may answer `/health` but cannot provide the v4 remote-control protocol. For full remote administration set the **server-side** ceiling:

```text
IRAS_REMOTE_SESSION_MAX_PERMISSION_LEVEL=3
```

Then on the laptop:

```powershell
.\setup-remote-windows.ps1 `
  -ServerUrl https://iras-cloud-abc1.onrender.com `
  -Mode full `
  -FullFileSystem
```

The script asks for `IRAS_API_TOKEN` through a PowerShell SecureString prompt. It is passed to `iras-device` through the process environment rather than command-line history, then persisted with Windows DPAPI. `-FullFileSystem` explicitly exposes `C:\` and, when present, `D:\` to IRAS file tools. Without it, file tools remain restricted to the normal IRAS roots.

Optional high-risk capabilities are **separate local opt-ins**:

```powershell
.\setup-remote-windows.ps1 -ServerUrl https://iras-cloud-abc1.onrender.com -Mode full -FullFileSystem -AllowPower -AllowCommand
```

`-AllowPower` permits remote restart/shutdown. `-AllowCommand` permits the critical `run_command` primitive. `run_command` still uses an explicit executable + argv with `shell=False`; using PowerShell/cmd itself is therefore an explicit full-admin choice.

## Remote use

Open the IRAS Cloud web client over HTTPS from a desktop or phone browser, enter the server URL and master API token for the current browser session, then click **Remote**. The web client:

1. finds an online paired Windows device;
2. asks for confirmation;
3. creates a short-lived remote session bound to that exact laptop;
4. stores the remote-session token in `sessionStorage` only;
5. sends subsequent chat requests with that session context.

The **Screen** button requests a bounded JPEG preview from the laptop. **Direct** opens a model-independent action console backed by the same `/v1/remote/invoke` endpoint, so core administration remains available even if an AI provider is unavailable. Normal chat can also use the registered Windows device tools: apps, UI observation/actions, verified text interaction, files, clipboard, processes, browser, Spotify/WhatsApp workflows, semantic verification, and—only when locally enabled—power or command execution.

The master API token is also kept in browser `sessionStorage`, not persistent `localStorage`.

## Two-key permission model

A cloud session alone cannot override the laptop.

- `read_only`: observation, screen preview, process/file reads, verification.
- `control`: adds ordinary GUI actions, safe file writes/moves, clipboard writes, app control.
- `full`: permits critical operations such as deletion. Restart/shutdown and command execution still require their dedicated laptop-side opt-ins.

The server additionally caps sessions through `IRAS_REMOTE_SESSION_MAX_PERMISSION_LEVEL`. A session is bound to one device, expires automatically, can be revoked, and its raw token is stored only as a hash server-side.

## Emergency stop

From the laptop:

```powershell
iras --emergency-stop
```

or inside IRAS:

```text
emergency stop
```

This trips a controller-level sentinel and disarms remote access. The outbound bridge refuses to execute commands while it is active.

To recover locally:

```powershell
iras --emergency-clear
iras --remote-arm full --remote-persistent
```

A remote client cannot clear the emergency stop.

For a remote-only stop without blocking local IRAS computer use:

```powershell
iras --remote-disarm
```

## Startup and uninstall

The setup script registers the visible Task Scheduler entry **IRAS Remote Windows Agent** at the current user's logon. It restarts after transient failures and runs only in the interactive user's session so Windows UI control works.
The task is allowed to start and remain running on battery. Windows sleep/hibernation is intentionally not changed automatically; for 24/7 reachability configure your preferred power plan separately.

Remove remote startup and disarm the laptop with:

```powershell
.\uninstall-remote-windows.ps1
```

## Operational limitations

Worldwide access depends on four independent components: the laptop must be powered on, Windows must have an interactive logged-in user for GUI tasks, Internet must be available, and the cloud service must be reachable. A locked workstation can still perform some file/process operations, but IRAS deliberately does not bypass the Windows secure desktop or login screen.
