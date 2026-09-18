# IRAS v5.0.0 RC3 — Complete Operating Layer

RC3 finishes the build-first production integration while intentionally avoiding quota-consuming cloud-provider acceptance tests.

## All-feature completion pass

The final RC3 completion audit uses a stricter definition than “module exists”: every declared feature family must have an implementation, a reachable control surface, permission enforcement where state changes, and local regression/contract coverage. RC3 now declares **32 feature families** and exposes **104 v5 model-facing tools** spanning autonomy, monitors, memory/knowledge, coding workspaces, workflow replay, notifications/mobile, connectors/vault, browser/voice/vision, artifacts, sandbox/capability learning, self-healing, research/debate/routing, signed skills, profiles/encrypted sync, home adapters, rollback/audit, goals and migrations.

Key completion hardening in this pass:

- Local schedules/research/debate attach to a real orchestration manager whose workers receive a separate **READ-only ToolRegistry**, preserving the interactive permission boundary.
- Connector lifecycle is operable (configure -> authorize -> connect -> invoke/disconnect), expires fail-closed, and built-in REST adapters are fixed-host and resolve credentials only through symbolic vault references.
- Signed skill verification authenticates the manifest **and SHA-256 of every packaged file**; installed skills can be re-verified for tampering.
- Android is versioned for RC3 and now registers as a companion, heartbeats through event polling, receives notifications, acknowledges per-device delivery and resolves approval prompts while retaining the existing chat/hands-free voice path.
- Schema migrations have a persistent ledger; profile sync exports/imports encrypted bundles via vault-referenced keys; home adapters remain allowlisted and approval-gated for state changes.
- The Control Center shows the feature matrix plus migrations, artifacts, recovery, capabilities and home-adapter state.
- `install.ps1` reuses an existing `.venv` instead of recreating an active environment.
- OmniParser provisioning preserves any unmanaged legacy `~/.iras/OmniParser` tree, creates a separate managed checkout, selects a free local port, updates `.env`, and defaults to rejecting reachable-but-unowned local services. External local lifecycle attachment requires explicit `IRAS_OMNIPARSER_ALLOW_EXTERNAL=true`.
- Deterministic release packaging excludes `.env`, VCS metadata, caches, compiled files and build debris.

See `RC3-FEATURE-MATRIX.md` for the complete 32-feature mapping.

## Production integrations completed

- Restart-safe scheduled autonomy with database leases, pause/resume, bounded concurrency and missed-run handling.
- Background proactive-monitor worker with intervals, retry backoff, pause/resume and change-only notifications.
- UIA + accessibility + OmniParser evidence fusion with conservative target scoring.
- Persistent Playwright profiles, multiple tabs, uploads, verification and approval-gated consequential submissions.
- Workflow recording/list/replay interfaces.
- Semantic memory namespaces with provenance, expiry and explicit deletion.
- Project knowledge graph snapshots retained from RC2.
- Persistent isolated Git workspaces with diff/test/merge-plan and approval-gated clean-repo merging.
- Learned recovery strategy statistics plus provider/browser/device/test recovery hooks.
- Versioned capability proposals with sandbox qualification, explicit install approval and uninstall support.
- Connector authorization state, symbolic secret readiness and vault-backed credential references for Gmail, Calendar, Drive, GitHub, Supabase, Discord, Slack and Notion.
- Full-duplex voice processing loop with wake state, VAD/STT/TTS injection and barge-in cancellation.
- Mobile companion device/event/approval queues.
- Browser/mobile/desktop notification plumbing.
- Existing DOCX/PDF/XLSX/PPTX/ZIP artifact engine retained.
- DPAPI/AES-GCM named secret vault retained.
- Docker-first no-network sandbox retained; unsafe local fallback remains disabled by default.
- Autonomous research and agent debate engines retained.
- Resource-aware local/cloud routing retained.
- Rollback timeline gains non-destructive preview.
- Audit filtering/export support.
- Signed skill installation gains inventory/uninstall lifecycle.
- Restricted home/network adapters remain allowlist + approval gated.
- Multi-user profiles gain updates and permission checks.
- Encrypted sync remains end-to-end AES-GCM.
- Goal hierarchy gains dependencies, readiness and automatic progress roll-up.
- Autonomy Control Center now exposes the complete feature matrix plus goal, schedule, monitor, memory, browser/workspace, artifact, recovery, capability, home-adapter, migration, connector/mobile/skills/profile status.

## Build-first rule

RC3 does not require Groq, Cerebras, Gemini, OpenRouter or other external model calls to build, install or validate local contracts. External connectors remain disconnected until explicitly authorized. Full real-device/API acceptance is deferred until provider quotas are available.

## Safety invariants

The v4.4 ToolRegistry, Remote authorization, device-bridge root restrictions, local Windows policy and emergency stop remain enforcement boundaries. Scheduled jobs are read-only by default, workspace merges/browser submissions/capability installs remain approval-gated, and secret values are not exposed through connector status or model-facing references.

## Managed OmniParser completion pass

- OmniParser is eager-started with normal IRAS CLI and device-bridge lifecycles instead of waiting for the first visual miss.
- A bounded watchdog re-probes and self-heals the local bridge after crashes.
- IRAS-owned bridges receive a random per-process control token and support authenticated stop/restart; reachable local but unowned services are rejected by default unless `IRAS_OMNIPARSER_ALLOW_EXTERNAL=true`, and remote endpoints are never process-managed.
- `install.ps1` now provisions all RC3 extras, Playwright Chromium, and the managed Microsoft OmniParser Python 3.12 environment/weights.
- `run-iras.ps1` performs preflight vision startup and automatically invokes idempotent provisioning/repair when the runtime is missing, unhealthy, or reachable but not IRAS-owned; legacy trees are preserved.
- `iras --vision-status/start/restart/stop` and model-facing vision lifecycle tools expose the managed runtime.
- Current Microsoft V2 detector/caption paths are used explicitly.
- The bridge defaults to EasyOCR and a fail-closed PaddleOCR stub to avoid the upstream eager Paddle/PyTorch DLL conflict on Windows while preserving full OmniParser visual semantics.
- `iras --doctor` now separates installation readiness from live endpoint readiness.

## Unified cloud workspace (Windows + web + Android)

- Added restart-safe cloud client presence, active thread metadata, transcript and non-secret preference storage on the v5 SQL backend.
- `/v1/chat` and `/v1/chat/stream` now accept stable `client_id`, `thread_id` and retry-safe `turn_id` metadata and return persisted message/thread IDs.
- Windows gains `iras-cloud-client` plus `run-iras-cloud-client.ps1` to join the same cloud thread as web/PWA and Android.
- Web/PWA and Android register stable client identities, resume the shared active thread and poll for cross-device messages.
- Direct agent context is request-scoped to the selected cloud thread; multi-agent seed context can carry the same thread ID.
- The cloud workspace stores no API/device/Remote/connector secrets. Local Windows ToolRegistry, Remote policy and emergency stop remain the final enforcement boundary.

