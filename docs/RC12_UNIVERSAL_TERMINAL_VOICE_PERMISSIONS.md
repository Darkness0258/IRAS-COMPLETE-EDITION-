# IRAS v5.0.0 RC12 — Universal Terminal + Voice Permissions

## Universal terminal

IRAS no longer needs a separate model-facing tool for Git, npm, pnpm, Bun, Cargo, Docker, GitHub CLI, AWS CLI, Supabase CLI, FFmpeg, Java, Gradle, or another installed command-line program.

Local terminal tools:

- `terminal_capabilities` — inspect shells/PATH and terminal runtime status.
- `terminal_discover` — dynamically enumerate PATH executables and PowerShell commands.
- `terminal_which` — resolve a CLI/cmdlet by name.
- `terminal_exec` — run a one-shot command with cwd, shell, stdin, env and timeout controls.
- `terminal_start` / `terminal_read` / `terminal_send` / `terminal_stop` / `terminal_sessions` — operate long-running or interactive CLI sessions.

There is intentionally no CLI-name allowlist. Tool authorization is attached to the requested operation. Normal terminal execution is `SYSTEM_ACTION`; known destructive patterns are promoted to `CRITICAL`. Master Control can authorize the complete registered terminal surface for its bounded local session. Emergency Stop, audit logging, Remote authentication/policy, filesystem roots where applicable, and Windows/UAC remain authoritative.

## Paired Windows / cloud clients

The bridge advertises `cli_discover` and the cloud registry exposes `device_cli_discover` as READ-only. `device_run_command` accepts any installed executable and argv with `shell=False`; use `powershell.exe` or `pwsh` plus `-Command` for PowerShell cmdlets/scripts. Remote execution remains CRITICAL and requires a full Remote session plus the laptop's explicit `allow_shell` policy.

Remote Protocol remains `1`.

## Voice authorization

Set in `.env`:

```dotenv
IRAS_VOICE_APPROVALS=true
IRAS_VOICE_APPROVAL_CRITICAL=true
IRAS_VOICE_APPROVAL_TIMEOUT=9
```

For an interactive `SYSTEM_ACTION`, IRAS speaks the permission request and accepts an explicit phrase such as:

```text
IRAS approve
```

A denial such as `IRAS deny` immediately denies that request. A bare `yes` is intentionally not enough.

For `CRITICAL` actions, IRAS generates and speaks a new four-digit challenge. Example:

```text
IRAS authorize seven four two nine
```

The challenge must match the current request. A stale approval phrase or generic background `yes` does not resolve the critical approval. If microphone recognition does not resolve the request, the CLI/desktop falls back to the existing typed/UI approval flow.

Voice authorization is not biometric speaker verification; recorded/replayed audio can potentially satisfy speech recognition. Master Control enablement therefore remains a separate local-owner action rather than being silently self-enabled by the agent.

## Repairing the local editable install

If pip reports `Access is denied ... .venv\\Scripts\\iras-device.exe` and subsequent IRAS commands fail with `ModuleNotFoundError`, run:

```powershell
cd D:\Projects\IRAS-complete
Set-ExecutionPolicy -Scope Process Bypass
.\repair-local-install.ps1
```

The repair script stops the IRAS Remote scheduled task if it is running, stops only IRAS console wrappers inside this project's `.venv`, reinstalls `.[all,cloud]`, verifies the import and Remote Protocol, and restarts the bridge task if it was previously running.
