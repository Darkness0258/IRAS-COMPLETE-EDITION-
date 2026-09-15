# IRAS 3.7.0 — Intelligent Responsive Autonomous System

IRAS is a local-first, permissioned AI agent for Windows and paired devices. It combines conversational AI, voice, files, browser/system tools, Windows UI control, persistent memory, automation, remote nodes, and a verified recovery loop for computer-use tasks.

The current development branch is **v3.7.0 multimodal**; the frozen stable release is **v3.6.0**. Historical milestone notes and one-off validators are intentionally not kept in the active tree; Git history is the release archive.

## Core capabilities

- Multi-step agent/tool loop with bounded execution.
- OpenRouter/OpenAI-compatible and Ollama-compatible providers.
- Persistent SQLite conversation/fact memory.
- Dynamic permission engine and audit logging with secret redaction.
- File, Git, browser, HTTP, system, application, screenshot, and scheduling tools.
- Voice output with Edge TTS and Windows fallback; optional local Whisper STT.
- CLI, Tkinter desktop UI, localhost FastAPI service, remote-node service, and paired clients.
- Windows computer control using semantic UI Automation plus a v3.7 multimodal scene graph for foreground/desktop vision.
- On-demand local OmniParser autostart for WebView/Electron/custom-rendered visual grounding when configured/discoverable.
- Stable grounded element IDs with confidence/provenance and one-state-changing-input-per-observation binding.
- Closed-loop `observe -> ground -> act -> re-observe -> verify` execution.
- Bounded recovery, adaptive route scoring, context-aware route learning, confidence calibration, stale-learning quarantine, and no failed-action replay.
- v3.6 ephemeral cross-app workflow memory with verification provenance and fresh destination grounding.
- Bounded autonomous decision supervisor: resolves safe session context, chooses next reversible steps, suppresses planner scratchpad, and keeps permissions/verification authoritative.

## Safety model

IRAS is built for systems, accounts, devices, and APIs you own or are authorized to operate.

Important invariants:

- Live computer state is authoritative over learned history.
- State-changing actions remain permission-gated.
- Critical actions require confirmation.
- Recovery observations do not prove task success by themselves.
- Failed click/type/send/submit actions are never automatically replayed.
- Cross-app workflow memory does not grant tool authorization.
- Destination UI targets must be freshly observed and grounded after an app switch.
- Persistent recovery learning stores aggregate route statistics, not screenshots, contacts, message contents, or target coordinates.

## Repository layout

```text
src/                 IRAS runtime packages
clients/             Android and web client sources
tests/               regression suite
scripts/              current release validators and maintenance helpers
docs/                 current documentation
ARCHITECTURE.md       system architecture
pyproject.toml        Python package metadata
run-v370-validation.ps1
run-v370-real-device-smoke.ps1
run-v360-validation.ps1          frozen v3.6 validator kept for release history
```

## Install on Windows

```powershell
cd D:\Projects\IRAS-complete
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
iras --doctor
```

For microphone transcription:

```powershell
pip install -e ".[voice,dev]"
```

For browser automation:

```powershell
pip install -e ".[browser,dev]"
playwright install chromium
```

## Configure a brain

OpenRouter is the default provider. Put secrets only in `.env`:

```env
IRAS_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here
IRAS_MODEL=openrouter/free
```

For Ollama:

```env
IRAS_PROVIDER=ollama
IRAS_BASE_URL=http://127.0.0.1:11434/v1
IRAS_MODEL=qwen2.5-coder:7b
IRAS_API_KEY=
```

Use a tool/function-calling model for autonomous workflows.

## Main commands

```powershell
iras                 # interactive agent
iras --doctor        # diagnostics
iras --tools         # capabilities
iras --voice-test    # TTS diagnostic
iras-desktop         # desktop UI
iras-api             # localhost API
iras-node             # authenticated remote node
iras-scheduler        # scheduled-prompt worker
```

Voice commands inside the CLI include `voice on`, `voice off`, `voice test`, and `listen`.

## Permission levels

| Level | Meaning | Typical examples |
|---|---|---|
| 0 | READ | read file, system info, Git status |
| 1 | SAFE_ACTION | launch normal app, open URL, create folder |
| 2 | SYSTEM_ACTION | shell execution, write/move files, browser click |
| 3 | CRITICAL | destructive delete, force push, dangerous shell patterns |

Levels 0–1 may run automatically under the default policy. Levels 2–3 require approval; critical actions remain explicitly confirmed.

## Windows computer control

IRAS uses a layered computer-use controller:

1. Observe the foreground or desktop.
2. Prefer semantic Windows UI Automation when actionable controls exist.
3. Escalate to foreground OmniParser grounding when UIA is insufficient; local OmniParser is auto-started on demand when configured/discoverable.
4. In auto scope, broaden once to desktop vision only if foreground grounding gives no usable result.
5. Fuse UIA + vision into a stable scene graph with confidence/provenance.
6. Act only against a fresh grounded observation/element binding; one state-changing input consumes that binding.
7. Re-observe and verify state plus semantic outcome.
8. If verification fails, select a bounded recovery route without replaying the failed state-changing action.

For the navigation-only WhatsApp goal “open a named chat and visually verify the
header without sending,” v3.7 includes a deterministic controller fast path. It
uses zero model rounds, never touches the message composer, and requires fresh
visual header proof before claiming success. Exact repeated visual parses may be
reused only when the freshly captured screenshot SHA-256 is identical.

See `docs/OMNIPARSER_IRAS_SETUP.md` and `docs/MULTIMODAL_GROUNDING_V3.7.0.md`.

## v3.6 cross-app workflow memory

Within one workflow, semantically verified facts can survive an app transition. The handoff records source-app and verification provenance, remains ephemeral, does not authorize tools, and requires the destination app to be freshly observed before the next action.

See `docs/CROSS_APP_WORKFLOW_MEMORY_V3.6.0.md`.

## Validation

Run the current v3.7 development validation before pushing:

```powershell
.\run-v370-validation.ps1
```

It performs:

- clean-tree/release hygiene checks,
- the integrated v3.6 safety-invariant validation,
- the v3.7 multimodal/autostart invariant validation,
- Python compile validation,
- the complete regression suite.

After pushing, run the read-only Windows device smoke test:

```powershell
.\run-v370-real-device-smoke.ps1
```

The smoke test reads system/UI state only; it does not click, type, send, submit, delete, or close anything.

## API and remote-node security

`iras-api` binds to localhost by default. If exposed over a network, configure a strong `IRAS_API_TOKEN` and put the service behind TLS/authentication. Remote nodes require a bearer token and enforce an independent permission cap.

Authenticated API secrets should be stored as `IRAS_SECRET_*` environment variables. The model references the variable name; raw secret values are injected inside the tool layer rather than placed in model tool arguments.

## Cloud and client docs

Current deployment/build documentation is under `docs/`:

- `docs/CLOUD_ARCHITECTURE.md`
- `docs/CLOUD_DEPLOY.md`
- `docs/RENDER_SUPABASE_DEPLOY.md`
- `docs/BUILD_APPS.md`

## Development rule

Keep the active tree focused on current code, current docs, regression tests, and current release tooling. Historical release notes belong in Git history rather than as duplicated root files or executable one-off validators.
