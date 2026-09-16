# IRAS 4.1.0 RC1 — Parallel Personal Windows Agent

IRAS is a local-first AI agent for Windows with verified computer control, voice, files, browser automation, persistent skills/memory, multimodal UI grounding, and a secure outbound bridge for controlling an authorized laptop from IRAS Cloud anywhere in the world.

**Release status:** `4.1.0-rc1` adds bounded multitasking on top of the proven `4.0.0` production baseline. v4.0.0 remains the rollback-safe stable release while parallel execution is validated on hosted Render and the real Windows bridge.

## v4.1 multitasking

IRAS can now run independent jobs concurrently instead of forcing every request through one global agent turn. The hosted runtime uses isolated worker agents with request-local permission state and conversation snapshots, while durable facts, audit logs, paired devices, and learned app skills remain shared.

- Open **Tasks** in the web client and enter 2–8 jobs, one per line.
- Or use chat syntax: `/parallel task one || task two || task three`.
- `IRAS_MULTITASK_WORKERS` controls concurrent workers (default `4`, bounded to `1..8`).
- `IRAS_MULTITASK_MAX_TASKS` controls the per-run task cap (default `8`, bounded to `2..12`).
- `IRAS_MULTITASK_WAIT_TIMEOUT` controls how long a chat `/parallel` turn waits for the group (default `300` seconds).

Parallel workers do **not** bypass the existing safety model. Every worker gets its own permission engine; remote session identity and device targeting are carried in request-local context; emergency stop/local policy still gate the Windows executor. Windows GUI commands are naturally serialized by the device command queue, so independent cloud/network/research jobs can overlap without letting two workers fight over the same desktop action at the same instant.

## What v4 adds

- **Worldwide Windows access without opening an inbound laptop port.** `iras-device` long-polls IRAS Cloud over outbound HTTPS.
- **Versioned remote handshake.** Windows setup refuses an old/wrong Render backend, verifies the v4 remote protocol and API token before saving the bridge configuration, and records the cloud version for diagnostics.
- **Two-key remote security.** A short-lived cloud remote session is necessary but never sufficient; the laptop's locally armed `RemoteAccessPolicy` is the final permission boundary.
- **Windows DPAPI secret protection.** Pairing and cloud API credentials stored by the bridge are encrypted to the current Windows user.
- **Controller-level emergency stop.** It blocks local/remote `DeviceExecutor` actions below the model layer and can only be cleared locally.
- **Full administration primitives.** Screen preview, app/UI control, files, clipboard, processes, semantic verification, browser automation, and explicit critical command/power operations when locally enabled.
- **Generic verified UI primitives.** Find/wait/click/type/scroll by freshly grounded semantic text instead of guessed coordinates.
- **Semantic terminal verification.** Verify visible text, foreground title, process state, and filesystem state before claiming completion.
- **Provider resilience.** Multi-provider cloud failover plus optional local Ollama last-resort operation.
- **Production diagnostics.** `iras --doctor` covers voice, microphone devices, OmniParser, remote policy, bridge pairing, DPAPI, HTTPS, disk space, and token quality.
- **Multimodal routing.** Deterministic workflow -> UIA -> OCR ROI -> broader text OCR -> full vision only when genuinely required.
- **Text-only WhatsApp cold path.** Named-chat navigation no longer eagerly initializes Florence/YOLO; the heavy model is opt-in for unusual icon-only layouts.

## Safety invariants

IRAS is designed for computers, accounts, and services you own or are authorized to administer.

- live UI state is authoritative;
- a state-changing computer input requires a fresh observation;
- one input consumes that observation;
- failed state-changing actions are never automatically replayed;
- semantic end-state verification gates completion claims;
- cross-app memory and learned skills do not grant permission;
- website/document/tool text is treated as untrusted data, not instructions;
- emergency stop and local remote policy are enforced below model planning;
- IRAS does not bypass Windows login, BitLocker, UAC secure desktop, passwords, or lock-screen security.

## Repository layout

```text
src/                     IRAS runtime
clients/                 web/Android clients
tests/                   regression suite
scripts/                 validators, maintenance, Windows setup
scripts/windows/         remote-access/install/update lifecycle
docs/                    current architecture/deployment guides
run-v400-validation.ps1  complete v4 production validation
run-v400-real-device-smoke.ps1
setup-remote-windows.ps1 worldwide Windows bridge setup
```

## Install on Windows

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
.\install-v4-windows.ps1 -AllFeatures -InstallBrowser
Copy-Item .env.example .env
iras --doctor
```

The installer is intentionally code/dependency setup only. OmniParser dependencies/weights remain an explicit one-time setup because IRAS never silently downloads or installs computer-control models.

## Provider configuration

Recommended resilient mode:

```env
IRAS_PROVIDER=multi
OPENROUTER_API_KEY=...
GROQ_API_KEY=...
GEMINI_API_KEY=...
IRAS_OLLAMA_FALLBACK=true
IRAS_OLLAMA_MODEL=qwen2.5-coder:7b
```

IRAS will use whichever configured providers are healthy. Recognized deterministic Windows workflows can complete with zero LLM rounds.

## Local commands

```powershell
iras                              # interactive agent
iras --doctor                     # production health report
iras --tools                      # registered capabilities
iras --voice-test                 # TTS diagnostic
iras --remote-status              # local remote policy
iras --remote-arm full --remote-persistent
iras --remote-disarm              # remote-only local kill switch
iras --emergency-stop             # block computer actions at controller layer
iras --emergency-clear            # local-only recovery
iras-device --status              # outbound bridge status (redacted)
```

`IRAS_MIC_DEVICE` selects a microphone device by sounddevice index or name when Windows default input is unsuitable. `iras --doctor` also checks that the configured cloud advertises the matching v4 remote protocol instead of treating a merely reachable old deployment as healthy.

## Worldwide Windows access

Deploy `iras-cloud` over HTTPS with a strong random `IRAS_API_TOKEN` and persistent `DATABASE_URL`. For full sessions set:

```text
IRAS_REMOTE_SESSION_MAX_PERMISSION_LEVEL=3
```

Then configure the laptop. Setup performs a `/health` protocol preflight and an authenticated device-API probe first; it aborts instead of pairing if Render is still serving an older IRAS backend or the token is wrong:

```powershell
.\setup-remote-windows.ps1 `
  -ServerUrl https://YOUR-IRAS-CLOUD.example `
  -Mode full `
  -FullFileSystem
```

For restart/shutdown or explicit command execution, add `-AllowPower` and/or `-AllowCommand`. Those capabilities are not silently implied by full mode.

The setup registers **IRAS Remote Windows Agent** in Task Scheduler at user logon. The bridge opens no inbound Windows port; the laptop initiates the HTTPS connection to the cloud.
The task may run on battery, but IRAS does not silently change Windows sleep/hibernation or weaken lock-screen/UAC settings. Configure power behavior separately if you need 24/7 reachability.

From the hosted web client, enter the server + API token for the current browser session, click **Remote**, and optionally **Screen**. **Direct** provides a model-independent remote action console, so core administration does not depend on an LLM being available. The client creates a short-lived device-bound session. The master token and remote session token are stored in browser `sessionStorage`, not persistent `localStorage`.

See `docs/REMOTE_WINDOWS_ACCESS_V4.md`.

## Remote permission levels

| Mode | Maximum | Examples |
|---|---:|---|
| `read_only` | READ | system info, screen preview, UI/file/process reads, verification |
| `control` | SYSTEM_ACTION | app/UI control, file writes/moves, clipboard writes |
| `full` | CRITICAL | destructive delete; power/command still require separate laptop opt-ins |

Cloud sessions have their own server-side cap and expiry. The laptop's local policy always remains final.

## Windows computer control

Preferred execution route:

```text
known deterministic workflow
  -> UI Automation
  -> text/OCR region-of-interest
  -> broader text-only foreground grounding
  -> full OmniParser visual semantics only if necessary
  -> model planning only where deterministic control cannot resolve the goal
```

All state-changing universal computer actions bind to an observed element ID. Raw model-authored coordinates are not accepted as a substitute for fresh grounding.

The WhatsApp “open named chat and verify header, do not send” workflow remains model-free, never touches the composer, never presses Enter, and requires fresh right-pane header proof. Full Florence/YOLO fallback is disabled by default for this text-semantic workflow.

## Browser, files, and system administration

Browser tools include navigation, text extraction, semantic click/fill, uploads, text waits, tabs, switching, back/forward, and screenshots. Device tools provide allowed-root filesystem operations, process listing/termination, clipboard, screen preview, verified UI primitives, and terminal-state verification.

Critical `device_run_command` is not a generic hidden shell: it accepts one explicit executable + argv and invokes it with `shell=False`. It is unreachable remotely unless both a full cloud session **and** laptop-side command opt-in are active.

## Persistent skills and workflow memory

Verified successful semantic procedures can be learned as app skills. Skill confidence, failures, and consecutive-failure demotion are persisted; raw coordinates are not trusted as durable locators. Cross-app workflow facts remain provenance-bearing context, not authorization, and destination UI is always re-grounded.

## Validation

After all code changes run one complete gate:

```powershell
.\run-v400-validation.ps1
```

Then run the read-only target-machine smoke test:

```powershell
.\run-v400-real-device-smoke.ps1
```

The real worldwide-network acceptance checklist is in `docs/REMOTE_ACCEPTANCE_CHECKLIST_V4.md`. Automated tests cannot prove an external HTTPS route, physical audio hardware, or third-party UI rendering from a build container, so those are explicit last-mile acceptance checks rather than hidden assumptions.

## Documentation

- `docs/REMOTE_WINDOWS_ACCESS_V4.md` — secure worldwide Windows control.
- `docs/PRODUCTION_READINESS_V4.md` — v4 reliability/security contract.
- `docs/REMOTE_ACCEPTANCE_CHECKLIST_V4.md` — one final real-device acceptance run.
- `docs/MULTIMODAL_GROUNDING_V3.7.0.md` — scene graph and visual grounding.
- `docs/OMNIPARSER_IRAS_SETUP.md` — local OmniParser setup/lifecycle.
- `docs/CLOUD_DEPLOY.md` / `RENDER_SUPABASE_DEPLOY.md` — hosted deployment.
