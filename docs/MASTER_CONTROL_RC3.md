# IRAS RC3 Master Control

Master Control is the owner-elevation mode for IRAS. It is intentionally **local-first**: only the Windows PC can turn it on. Web, Android, and the cloud client can attach a full Master Remote session only after the PC reports that Master Control is already active.

## What Master Control grants

While active, IRAS may execute registered tools through `CRITICAL` without per-action approval prompts. Local Master Control also arms the existing Windows Remote policy in `full` mode with command execution and power actions enabled, and it can allow multi-agent workers to use the same registered tool surface rather than the normal READ-only worker cap.

This means IRAS can use, when already configured and authorized:

- full registered filesystem actions inside the device bridge roots;
- app/browser/computer control and OmniParser;
- shell-safe `run_command` execution (`shell=False`, explicit executable + argv);
- process and power actions;
- coding, Git, artifacts, connectors, browser, device and v5 tools;
- bounded autonomous/multi-agent execution when `autonomous=true`.

Master Control does **not** bypass Windows UAC/secure desktop, BitLocker/login authentication, endpoint protection, service/account authentication, the emergency stop, Remote tokens, bridge filesystem roots, or audit logging.

## Local owner activation

Status:

```powershell
iras --master-status
```

Enable for 30 minutes:

```powershell
iras --master-enable 30
```

IRAS requires the exact local confirmation phrase:

```text
ENABLE MASTER CONTROL
```

Disable and restore the previous Remote policy:

```powershell
iras --master-disable
```

A persistent mode exists for dedicated owner-controlled hosts:

```powershell
iras --master-enable 30 --master-persistent
```

Prefer bounded sessions for daily use.

## Desktop

`iras-desktop` has a **Master Control** item in the sidebar. Enabling it requires the same local confirmation phrase and defaults to 30 minutes. The button shows the remaining time and can disable the mode immediately.

## Windows cloud client

Inside `iras-cloud-client`:

```text
/master
/master on
/master on 60
/master off
```

`/master on` first performs the local owner confirmation when needed, then creates an ephemeral FULL Remote session and attaches it to cloud chat. The remote-session token is kept only in process memory and is revoked when the client exits.

## Web/PWA

The sidebar contains **Master**. Web cannot turn local Master Control on. It checks the paired PC through `system_info`; if the PC is not locally armed it tells you to run:

```powershell
iras --master-enable 30
```

Once the PC is armed, **Attach Master Session** creates a bounded FULL Remote session and chat/direct actions automatically carry that session.

## Android

The Android header contains a **Master** button. Like web, Android cannot enable the local PC elevation. It creates a FULL Remote session, verifies the PC's `master_control.enabled` state through `system_info`, and only keeps the session when that local owner switch is active. Cloud chat then carries the Master Remote headers until the session expires or you end it.

## Emergency stop

Emergency stop always wins:

```powershell
iras --emergency-stop
```

A tripped emergency stop disables Master Control and prevents device execution. Clearing the stop does not silently re-enable an expired/disabled Master session.

## Cloud configuration

Master Remote sessions require the cloud Remote-session ceiling to allow `CRITICAL`:

```env
IRAS_REMOTE_SESSION_MAX_PERMISSION_LEVEL=3
```

The provided Render blueprint already uses `3`. The local Windows Master state remains the final owner-controlled gate for shell/power execution.

## Deterministic Quick Code path

Master Control no longer sends simple coding requests such as **“open VS Code and write a Python hello-world/triangle program”** through the generic GUI planner. IRAS exposes a specialized `device_quick_code` tool that generates the requested source, creates the file inside an allowed bridge root, reads the file back to verify the exact contents, opens the workspace in VS Code, and terminates the turn immediately with a verified result. This avoids tool-step exhaustion and editor-typing races while preserving the same filesystem and Remote permission enforcement.

## Emergency Adaptive execution profile

Master Control now replaces ordinary small execution budgets with the Emergency Adaptive profile documented in `EMERGENCY_MASTER_EXECUTION.md`.

Default high-capacity values are 256 agent steps, 128 parallel/orchestration tasks, 32 active runs, 24 recovery attempts, 24-hour provider wait, and a 6-hour runaway watchdog. Verified Web/Android/Cloud Master sessions inherit the same profile through the `master` Remote-session scope.

The owner-intent rule is **no ordinary refusal**: IRAS does not stop simply because an authorized task is long, complex, repetitive, expensive, or needs many tool calls. It continues/replans until verified completion or a concrete blocker. This is not an instruction to bypass emergency stop, authentication, Windows/UAC/account controls, configured device/filesystem boundaries, audit/verification requirements, or applicable safety/security restrictions.
