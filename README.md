# IRAS 5.0.0 RC3 — Complete Autonomous Operating Layer

IRAS v5 builds on the frozen v4.4 permissioned Windows/control core and adds a modular autonomous operating layer with **33 validated feature families**: persistent schedules, proactive monitoring, managed multimodal vision, dedicated browser workflows, project knowledge, isolated coding workspaces, semantic memory, workflow recording/replay, lifecycle-managed connectors, full-duplex voice coordination, mobile/Android approvals, notifications, artifacts, encrypted secrets/sync, sandboxed capability learning, research/debate agents, resource-aware routing, rollback/audit, signed skills, home adapters, multi-user profiles, schema migrations, a Control Center, and deterministic release engineering.

**Release status:** `5.0.0-rc3`. The remote protocol remains `1`; v5 does not weaken the v4.4 device bridge, Remote-session, local-policy, emergency-stop, or ToolRegistry boundaries.

## Professional UI/UX & motion system

RC3 now ships one visual language across Web/PWA, the native Windows desktop shell, and Android: a restrained dark command-center aesthetic, clear surface hierarchy, adaptive navigation, polished message/composer states, purposeful micro-interactions, and accessibility-aware motion. The web client honors `prefers-reduced-motion`; Android handles modern system-bar insets and accessibility labels; the desktop shell adds structured chat, custom approvals, and native motion feedback without adding a GUI framework dependency. See `docs/UI_UX_PROFESSIONAL_RC3.md`.

## v5.0 RC3 complete operating layer

- **Complete control surface:** all 33 feature families are reachable through model-facing tools, API/UI status surfaces, or dedicated lifecycle commands; RC3 exposes 100+ v5 tools through the normal permissioned ToolRegistry.
- **Autonomy Control Center:** web UI exposes the full feature matrix plus schedules, monitors, goals, notifications, artifacts, recovery, capabilities, home adapters, migrations, connectors, and audit summaries.
- **Persistent autonomy:** v5 state uses PostgreSQL when `DATABASE_URL` is configured and SQLite locally; local schedule/research/debate workers run through a separate READ-capped ToolRegistry.
- **Safe extensibility:** generated capabilities require sandbox tests + explicit approval; signed marketplace skills authenticate the manifest **and every package file hash** with Ed25519.
- **Lifecycle-managed integrations:** connectors fail closed on missing authorization/expired credentials; Android RC3 registers, heartbeats, receives per-device events, acknowledges delivery and resolves approval prompts.
- **Unified cloud workspace:** Windows (`iras-cloud-client`), web/PWA and Android share restart-safe cloud client presence, one active conversation, synchronized message history and non-secret preferences through the same authenticated Cloud API.
- **No automatic merge / no secret exposure / no ambient network scanning:** high-impact operations remain explicit and bounded.

See `RC3-FEATURE-MATRIX.md` and `docs/V5_0_RC3_NOTES.md` for the complete capability inventory.

## v4.4 FINAL production hardening

- **Verified provider health:** cloud providers remain `CONFIGURED` until an authenticated probe or real request proves reachability; the Providers panel now actively probes without generating text.
- **Shared health-aware routing:** multi-agent worker pools share cooldown/failure telemetry and can prefer healthier fallbacks after repeated failures.
- **Durable deployment checkpoints:** when `DATABASE_URL` is set, orchestration checkpoints are mirrored to PostgreSQL instead of depending only on Render's ephemeral filesystem.
- **Guarded rollback:** terminal engineering jobs can restore tracked working-tree changes to their captured Git HEAD after explicit FULL Remote authorization; commit rewrites and untracked-file deletion are refused.
- **Eight-hour job watchers:** browser progress/result polling now matches long provider recovery windows.
- **Final release CI:** Windows Actions validates the v4.4 FINAL release script.

## v4.4 RC2 provider status + CI hotfix

- **Current-release CI:** GitHub Actions now runs `run-v440-validation.ps1` instead of the stale v4.3 validator.
- **Provider card de-duplication:** server and web UI collapse repeated provider identities, including device-local Ollama.
- **Refresh race protection:** overlapping Providers-panel refreshes cannot append duplicate cards.
- **No protocol change:** Remote protocol remains `1`; all v4.4 RC1 persistent-autonomy behavior is preserved.

## v4.4 RC1 persistent autonomy and provider health

- **Provider Status panel:** live state, model, cooldown, latency, last error/success, active provider, next provider, and device-local Ollama readiness.
- **Health-aware failover visibility:** provider cooldown/rate-limit/auth/offline states are exposed through `/v1/providers/status` and used by the existing provider circuit breaker.
- **Durable autonomous checkpoints:** completed DAG nodes and verified project/rollback metadata survive cloud restarts. Running nodes are never replayed automatically.
- **Explicit restart resume:** interrupted jobs restore as `interrupted`; Resume re-queues only unfinished nodes while preserving completed evidence. State-changing work requires fresh Remote authorization after restart.
- **Retry Failed:** re-queues failed/blocked nodes without discarding successful checkpoint nodes.
- **Progress history:** job events record planning, node starts/completions, provider/device waits, restart recovery, resume/retry, and terminal outcomes.
- **Rollback metadata:** engineering preflight captures the verified project root, current Git HEAD, and whether the working tree was clean before autonomous edits begin.

## v4.3 RC8 responsive device bridge

RC8 separates paired-device Ollama inference from the main outbound polling loop. Long local-AI generation can no longer stop device heartbeats or make ordinary Windows actions appear offline. While local inference is active, the bridge keeps polling and temporarily asks the cloud to skip additional `local_llm_complete` commands, leaving app/file/Git/test work claimable. Safety and Remote authorization gates are unchanged.

## v4.3 RC7 project identity & local tool execution

- Named project discovery cannot silently substitute an unrelated repository.
- Project scanning allocates a bounded budget per allowed bridge root, preventing a large `C:\Users` tree from starving `D:\Projects`.
- Cloud preflight independently re-validates project identity before binding the DAG.
- Device-local Ollama content-only JSON tool requests are normalized into real IRAS tool calls when—and only when—the tool was supplied in the current schema.
- Local-provider assistant messages now preserve valid OpenAI-style `role/content/tool_calls` structure across tool rounds.
- Existing Remote authorization, verified project-root binding, permission levels, emergency stop, and protocol `1` remain unchanged.

## v4.3 RC6 device-local AI failover

When every configured cloud AI provider is unavailable, specialized multi-agent workers can now continue through an Ollama model running locally on the paired Windows PC. The cloud never connects to the laptop directly: the request travels through the authenticated outbound-only device bridge, and the Windows executor may contact only a loopback Ollama endpoint. Local-model tool calls still pass through the same ToolRegistry permissions, verified project root, Remote session, laptop-local policy, and emergency stop. `iras --doctor` reports local fallback readiness and detected models.

## v4.3 RC5 remote authorization continuation

- Browser engineering-intent preflight recognizes noun forms such as `improvement` as well as `improve`.
- Normal streaming chat treats `execution_mode=authorization_required` as a resumable safety checkpoint.
- After the user explicitly approves the 30-minute FULL Remote session, IRAS retries the exact pending chat turn once with the new Remote headers; the user message is not duplicated.
- Tasks → Start Goal performs the same one-time authorization continuation when the server returns a Remote-session 403.
- Declining Remote consent leaves the state-changing objective unstarted.
- The server-side Remote safety gate remains authoritative; IRAS never self-grants Windows authorization.
- RC3/RC4 protections remain intact: main-chat final-result delivery, truthful partial-failure status, verified project-root binding, project preflight, and engineering Planner quality enforcement.

## v4.3 RC2 project-aware engineering preflight

Before an engineering DAG starts, IRAS now verifies the target Windows device is online, discovers repositories only inside the device's configured bridge roots, selects the requested project (for example `IRAS`), and proves that Git can read the resolved workspace. The resulting Windows project root is injected into every worker as authoritative context, so Coder/Tester/Reviewer agents no longer guess Render/container paths or unrelated local repositories.

A new read-only `device_find_projects` capability performs bounded repository discovery without following symlinks. If several projects exist and the request does not identify one, IRAS fails early and asks for the project name/path rather than selecting an arbitrary repository. If the project is not under the configured bridge roots, the run is rejected before the graph starts with the actual allowed roots in the diagnostic.

Temporary bridge outages during an already-running graph now use `IRAS_ORCHESTRATION_DEVICE_WAIT_SECONDS` (default `180`, bounded `0..900`). These waits do not consume the task's normal retry budget. The Tasks UI shows `device wait` just like provider cooldown waits. Permission/root errors remain hard failures and are never retried as if they were connectivity problems.


## v4.3 RC1 deep audit hardening

RC1 treats every web/API/browser result as untrusted external data before it is returned to the model. Retrieval metadata explicitly marks trust level and common prompt-injection signals. Tool arguments are schema-validated before authorization/execution, and audit redaction covers bearer/env/JWT/common provider token shapes even when secrets are embedded inside generic strings.

The Windows/project tool surface is now better suited to real engineering work without adding arbitrary shell access: `device_read_text_range`, `device_search_text`, `device_file_info`/SHA-256, `device_git_diff`, `device_git_log`, and targeted `device_run_tests`. File writes/replacements are atomic, recursive copies fail closed on symlinks, searches skip credential paths, and sensitive files/process termination dynamically require `CRITICAL` permission. Device tool permission resolvers now use the exact remote action and arguments so the cloud permission gate and laptop-local policy cannot silently disagree.

Public web/API retrieval is bounded by response size/content type, rejects embedded URL credentials and unsafe headers, and validates public redirect targets. Orchestration and multitasking enforce per-requester active-run caps. Observable orchestration history survives Render restarts, but interrupted runs are marked failed and are never automatically replayed.

## v4.2 autonomous chat execution

Normal chat is now the primary interface. IRAS applies a local provider-independent execution router before calling an LLM:

- simple conversation or one action -> **Direct**;
- exact bounded file write/verify requests -> **Deterministic**;
- clearly independent jobs -> **Parallel** execution;
- dependent build/fix/test/review workflows -> **Multi-agent DAG**.

The router is conservative so ordinary conversation is not over-split. `/parallel` and `/goal` still force a mode when you explicitly want one. `IRAS_AUTONOMOUS_EXECUTION=true` enables automatic routing (default), and `IRAS_AUTONOMOUS_WAIT_TIMEOUT=600` bounds synchronous automatic parallel waits.

IRAS never self-grants Windows authority. When a deterministic state-changing request needs a Remote session, the web client prompts you to authorize one and the server refuses to start that state-changing graph without it.

## v4.2 RC6 specialized execution

RC6 gives each orchestration role a narrow capability set instead of relying on the generic smart-tool router. Researcher workers use `web_search` and readable `http_get` for public web research; they do not need to open Chrome or visually scrape a page. Coder workers can inspect project files, apply an exact bounded `device_replace_text` patch, create a small/new file with `device_write_text`, inspect git status, and run the bounded project test runner. Arbitrary shell is not added.

`device_replace_text` is a `SYSTEM_ACTION` and only works inside configured Windows bridge roots. It requires an exact expected snippet, bounds file/snippet/replacement size, and still passes through Remote-session permission, laptop-local policy, the authenticated command queue, and emergency stop.

If the model Planner is unavailable, implementation goals fall back to a local `Inspect -> Coder -> Tester -> Reviewer -> Coordinator` DAG instead of one broad worker. `IRAS_ORCHESTRATION_AGENT_MAX_STEPS` defaults to `14` (bounded `8..24`) for specialized graph workers only.

## v4.2 multi-agent execution

Give IRAS one objective and it can plan and supervise the work instead of requiring you to manually split every step. The Planner creates a bounded DAG for specialized Researcher, Coder, Tester, Reviewer, General, and final Coordinator workers. Independent nodes run concurrently; dependent nodes wait for verified upstream completion.

- Web: **Tasks → Multi-agent objective → Start Goal**.
- Chat: `/goal your objective here` (aliases: `/orchestrate`, `/agents`).
- Pause/resume/cancel are available from the Tasks panel and API.
- Priorities, dependencies, attempts, retries, states, errors, and the final Coordinator result are observable.
- `IRAS_ORCHESTRATION_WORKERS` controls graph workers (default `4`, bounded `1..8`).
- `IRAS_ORCHESTRATION_MAX_TASKS` controls planned graph size (default `12`, bounded `2..20`; the final Coordinator is added automatically).
- `IRAS_ORCHESTRATION_PROVIDER_WAIT_SECONDS` controls how long graph tasks automatically wait through temporary all-provider cooldowns before consuming their normal task retry budget (default `21600` (6 hours), bounded `0..86400`).
- `IRAS_ORCHESTRATION_AGENT_MAX_STEPS` controls the bounded tool-step budget for specialized graph workers only (default `14`, bounded `8..24`).

For exact text-file goals of the form `Create C:\path\file.txt containing exactly "..."`, RC6 uses the same deterministic executor in both Direct chat and multi-agent Tasks: only `write_text`, `read_text`, and `git_status` are allowed, state-changing writes still require an active Remote session, and Windows allowed-root/local-policy/emergency-stop checks remain authoritative. This path does not execute shell commands.

IRAS v4.1 `/parallel` mode remains available for independent jobs. Multi-agent workers do **not** bypass the existing safety model: each worker has isolated permission state and conversation context; remote session/device targeting remains request-local; upstream outputs are treated as untrusted data; Windows commands still pass through the authenticated queue, local policy, and emergency stop.

## v4.1 parallel multitasking

- Open **Tasks** and enter independent jobs, one per line, then choose **Run Parallel**.
- Or use `/parallel task one || task two || task three`.
- `IRAS_MULTITASK_WORKERS` defaults to `4` (bounded `1..8`).
- `IRAS_MULTITASK_MAX_TASKS` defaults to `8` (bounded `2..12`).
- `IRAS_MULTITASK_WAIT_TIMEOUT` defaults to `300` seconds.

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
run-v420-validation.ps1  complete v4.2 multi-agent validation
run-v500-validation.ps1  v5.0 RC3 complete operating-layer validator
run-v400-real-device-smoke.ps1
setup-remote-windows.ps1 worldwide Windows bridge setup
```

## Install on Windows

From the project root:

```powershell
.\install.ps1
```

`install.ps1` now provisions the complete local operating layer: it reuses an existing IRAS virtual environment when present, installs all RC3 extras and Playwright Chromium, and provisions an isolated Python 3.12 Microsoft OmniParser checkout with the V2 detector/caption weights. If `%USERPROFILE%\.iras\OmniParser` already contains an unmanaged/legacy installation, IRAS preserves it and creates a separate `OmniParser-iras-managed` checkout instead of overwriting it. The managed service is then started and probed before installation completes.

Normal local/device-first startup is:

```powershell
.\run-iras.ps1
```

To join the same cloud conversation used by the web/PWA and Android clients from Windows:

```powershell
.\run-iras-cloud-client.ps1
# or
iras-cloud-client
```

Set `IRAS_CLOUD_URL` to the deployed HTTPS server and `IRAS_CLOUD_TOKEN` (or `IRAS_API_TOKEN`) to the Cloud access token. The Windows cloud client persists only its non-secret client/thread IDs under `~/.iras/cloud-client.json`; tokens remain in environment/private `.env` configuration.

The launcher requires an IRAS-owned OmniParser bridge by default before entering chat. A reachable-but-unowned local service is treated as migration-needed, so `run-iras.ps1` invokes the idempotent provisioning/repair flow, preserves the legacy tree, selects a free managed port in `8010-8020`, updates `.env`, and starts the owned bridge. Set `IRAS_OMNIPARSER_ALLOW_EXTERNAL=true` only when you explicitly want to attach to an externally managed local OmniParser lifecycle; `IRAS_OMNIPARSER_AUTOSTART=false` disables managed startup.

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
iras --vision-status              # managed OmniParser state
iras --vision-start               # start/attach managed vision runtime
iras --vision-restart             # authenticated restart of IRAS-owned bridge
iras --vision-stop                # authenticated stop of IRAS-owned bridge
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

For the complete daily startup/deployment checklist covering **PC + Cloud + Web + Android + OmniParser + Remote**, see `docs/RUN_IRAS_FULL_STACK.md`.

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

OmniParser is an IRAS-owned subsystem by default: eager startup, background EasyOCR warmup, a bounded health watchdog, authenticated stop/restart control, and automatic recovery are built in. Setup performs a real full-model Florence/YOLO smoke test, while normal runtime may still lazy-load the heavy model until a visual-only interface requires it. Reachable local services that IRAS does not own are rejected by default rather than silently weakening lifecycle guarantees.

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
.\run-v500-validation.ps1
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

## RC3 risk-based approvals and reliable media control

Local interactive use no longer asks for approval for bounded routine actions such as opening/focusing apps, Spotify search/play, media controls, opening a WhatsApp chat without sending, and bounded scrolling. Approval remains required for consequential operations such as generic click/type workflows that can submit actions, file mutation/deletion, shell or command execution, process/power control, external submissions/writes, connector authorization, home-control commands, installs, rollback, and other elevated operations. Remote-session action classification remains unchanged and continues to be enforced by the Remote authorization layer.

Spotify playback now follows a deterministic sequence: open/focus Spotify, wait for the real window to become ready, enter the query, wait for the search UI to settle, then issue Spotify's own play action. URI navigation and the visually detected green Play button are compatibility fallbacks rather than startup-racing primary paths.

