# IRAS RC3 — Full-Stack Run Guide (PC + Cloud + Web + Android)

This guide starts the complete IRAS stack while preserving the v4.4 security boundaries, Remote authorization, emergency stop, and protocol `1`.

## 1. One-time Windows installation

Open PowerShell in the project root:

```powershell
cd D:\Projects\IRAS-complete
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

If you only replaced project files and already have a healthy `.venv`:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[all,cloud]"
python -m playwright install chromium
```

Verify the local machine:

```powershell
iras --doctor
iras --vision-status
iras --remote-status
```

Expected essentials: Python/Git/voice PASS, OmniParser `ready=true`, Remote protocol `1`, emergency stop clear, and the cloud server reachable.

## 2. Private `.env`

Keep `.env` private and out of Git. A practical configuration is:

```env
IRAS_PROVIDER=multi
IRAS_OLLAMA_FALLBACK=true
IRAS_OLLAMA_MODEL=qwen2.5-coder:7b
IRAS_CLOUD_URL=https://iras-cloud.onrender.com
IRAS_CLOUD_TOKEN=YOUR_CURRENT_IRAS_API_TOKEN
```

Add only the provider keys you actually use. The Cloud token on the PC must match Render's `IRAS_API_TOKEN`.

## 3. Start the local/device-first IRAS

```powershell
cd D:\Projects\IRAS-complete
.\.venv\Scripts\Activate.ps1
.\run-iras.ps1
```

This is the process that owns the local Windows tools, voice, OmniParser, Spotify/media automation, browser/device actions and local approval boundary.

For the native desktop shell instead:

```powershell
iras-desktop
```

## 4. Keep the outbound Windows bridge online

First-time pairing:

```powershell
.\setup-remote-windows.ps1 `
  -ServerUrl https://iras-cloud.onrender.com `
  -Mode full `
  -FullFileSystem
```

Only add `-AllowPower` or `-AllowCommand` if you intentionally want those critical capabilities.

Useful checks:

```powershell
iras-device --status
iras --remote-status
iras --remote-arm full --remote-persistent
```

The bridge is outbound-only and normally starts through the **IRAS Remote Windows Agent** scheduled task. The cloud cannot bypass the laptop's local policy or emergency stop.

## 5. Start/join the unified Cloud conversation from PC

```powershell
iras-cloud-client
```

Useful commands inside it:

```text
/new
/history
/exit
```

This joins the same persistent thread used by Web and Android. It is a cloud chat client; keep the local IRAS/device bridge online when you want it to control the PC.

## 6. Web/PWA

Open:

```text
https://iras-cloud.onrender.com
```

In **Settings**, enter the same Render `IRAS_API_TOKEN`. Use **Remote** to create a short-lived device-bound session when PC state must change. `Remote: full` means the session is attached; local Windows policy is still the final boundary.

The new **New chat** button creates and activates a fresh shared Cloud thread without deleting previous history.

Routine bounded actions such as Spotify/media do not prompt. Consequential actions such as arbitrary typing/clicking, file mutation, shell/process/power operations, sends/submits, installs and rollback remain approval-gated.

## 7. Android

Build the APK from GitHub Actions **Build Android APK**, or locally from `clients/android` with Android SDK 35/Build Tools 35 and Gradle 8.10.2.

After installing the APK:

1. Open **Settings**.
2. Server: `https://iras-cloud.onrender.com`.
3. Token: the current `IRAS_API_TOKEN`.
4. Allow microphone/notification permissions if desired.
5. Keep Cloud sync enabled and use the same shared thread.

Android receives companion events and approval prompts and can approve/deny consequential actions.

## 8. Managed vision / OmniParser

Normally `run-iras.ps1` starts it automatically. Manual checks:

```powershell
iras --vision-status
iras --vision-start
```

If repair is actually needed:

```powershell
.\setup-omniparser.ps1 -Repair
```

Healthy state should include `ready=true`, `text_model_loaded=true`, `full_model_loaded=true`, and `full_model_error=null` after the full model has warmed.

## 9. Recommended daily startup

For full PC + Cloud capability, keep these two roles available:

**Device/local role**

```powershell
cd D:\Projects\IRAS-complete
.\.venv\Scripts\Activate.ps1
.\run-iras.ps1
```

**Cloud conversation role (optional separate terminal)**

```powershell
cd D:\Projects\IRAS-complete
.\.venv\Scripts\Activate.ps1
iras-cloud-client
```

The web and Android clients can then share the same Cloud thread while the outbound Windows bridge gives that authenticated session access to the authorized PC.

## 10. Fast troubleshooting

### `iras-cloud-client` is not recognized

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[all,cloud]"
```

### Cloud returns `401 Invalid IRAS access token`

Make `IRAS_CLOUD_TOKEN` on the PC match `IRAS_API_TOKEN` on Render. Rotate any token that has been exposed publicly.

### Web says no paired PC is online

```powershell
iras-device --status
iras --remote-status
```

Then start/reinstall the outbound bridge if needed.

### A risky operation is not executed

That is expected when approval is required. Approve it from the active approval UI/companion rather than weakening the global security boundary.

### Spotify/media does not play

Keep Spotify signed in and running normally. IRAS now searches/selects/plays and verifies the actual query context rather than accepting unrelated playback.

### Emergency stop is active

Only clear it locally when you intentionally want computer actions again:

```powershell
iras --emergency-clear
```

## 11. Release validation

Before deploying a new build:

```powershell
.\run-v500-validation.ps1
```

Then push `main`; Render auto-deploys the Cloud service. Confirm `/health`, GitHub Actions, and one PC/Web/Android shared-thread test before treating the release as production-ready.

### RC3 remote pairing compatibility

`setup-remote-windows.ps1` validates the deployed cloud by `service_id=iras-cloud` and `remote_protocol=1`. The release version string is informational, so protocol-compatible RC3/v5 cloud releases are accepted instead of being rejected by the old v4-only version guard.
