# IRAS v5.0.0 RC4 — Complete Feature Matrix

RC4 declares **36 operating-layer feature families**. A feature is counted only when its implementation is present, reachable through an IRAS control surface, protected by the existing authorization model where state can change, and covered by local regression/contract tests.

| # | Feature | Operational surface |
|---:|---|---|
| 1 | Persistent scheduled autonomy | Persistent schedules, leases, worker loop, pause/resume/cancel; local background workers are READ-capped |
| 2 | Proactive monitoring | HTTPS/API/disk monitors, leases/backoff, pause/resume, change notifications |
| 3 | Advanced visual computer agent | UIA/accessibility evidence plus conservative visual fusion and fresh verification |
| 4 | Managed vision runtime | IRAS-owned OmniParser bootstrap, eager start, watchdog, authenticated lifecycle, legacy-tree preservation |
| 5 | Dedicated browser agent | Persistent Playwright profile, tabs, navigation, extraction, fill/click/upload/submit verification |
| 6 | Workflow recording | Record/list/replay through ToolRegistry rather than direct execution |
| 7 | Long-term semantic memory | Namespaces, provenance, persistent token index, expiry and explicit deletion |
| 8 | Project knowledge graph | Authorized repository indexing and graph snapshots |
| 9 | Isolated coding workspaces | Git worktrees plus dedicated Coding Agent, verified project binding, diff/tests/review and permissioned Windows/VS Code controls |
| 10 | Self-healing workflows | Recovery statistics and bounded recovery hooks without replaying consequential actions |
| 11 | Capability learning | Proposal, sandbox qualification, install inventory and uninstall lifecycle |
| 12 | Plugin connector layer | Connector lifecycle, vault refs and expiry fail-closed |
| 13 | Full-duplex voice runtime | VAD/STT/TTS coordinator, wake state and barge-in cancellation surface |
| 14 | Mobile companion hub | Device registry, heartbeat, event delivery/ACK and approval queue |
| 15 | Android companion | Shared cloud chat/voice, companion events and approval UI |
| 16 | Notification system | Browser/mobile/desktop event persistence and read state |
| 17 | Artifact engine | DOCX, PDF, XLSX, PPTX and bundle generation/listing |
| 18 | Secure secrets vault | Symbolic refs only; DPAPI on Windows / AES-GCM master-key mode elsewhere |
| 19 | Sandbox execution | Docker-first no-network Python execution; local fallback remains explicit opt-in |
| 20 | Autonomous research projects | General orchestrated research/review task graph with READ-capped workers |
| 21 | Dedicated Web Research Agent | `/research` discovery → evidence collection → cross-check → review → synthesis using public web tools only |
| 22 | Permissioned Software Installer Agent | `/install` WinGet exact-ID path plus verified HTTPS `.exe`/`.msi` path; CRITICAL execution stays behind Remote/local policy/UAC |
| 23 | Agent debate review | Proposal/challenge/test orchestration with bounded worker roles |
| 24 | Resource-aware intelligence | Resource/provider routing surface with local-safe fallback paths |
| 25 | Rollback timeline | Git checkpoint capture, preview and approval-gated restore |
| 26 | Activity/audit dashboard | Filtered audit summary/rows plus Control Center display |
| 27 | Signed skill marketplace | Ed25519 signature over manifest and installed file hashes, verify/install/uninstall |
| 28 | Home network adapters | Fixed allowlist, no ambient scanning, read status and approval-gated state changes |
| 29 | Multi-user profiles | Create/update/list permission namespaces |
| 30 | Encrypted sync | AES-GCM profile/memory bundles using vault-referenced keys and sync journal |
| 31 | Goal hierarchy | Goal/project/milestone/job/task tree, dependencies, readiness and progress roll-up |
| 32 | Schema migrations | Persistent migration ledger and indexed schema upgrades |
| 33 | Control Center UI | Feature matrix plus autonomy/artifact/recovery/capability/home/migration status |
| 34 | Unified cloud workspace | Restart-safe client presence, shared active thread/history/preferences across Windows, web/PWA and Android |
| 35 | Master Control | Local owner elevation with CRITICAL registered-tool authority, shell/power opt-in and emergency-stop/audit preservation |
| 36 | Release engineering | Clean-tree/integrated validators, deterministic package builder and release manifest |

## RC4 installer enforcement

Software installation is intentionally not an unrestricted "download and execute anything" primitive. The preferred route is WinGet package discovery plus exact package ID. Direct web installation accepts only public HTTPS `.exe`/`.msi` downloads, stores them in the IRAS installer cache, records SHA-256, requires a valid Authenticode signature at preparation and immediately before execution, and never accepts an arbitrary local executable path. Windows UAC, SmartScreen, Remote authentication, local Remote policy, ToolRegistry authorization, configured roots, audit and emergency stop remain authoritative.

## Preserved enforcement boundary

Remote protocol remains **1**. RC4 does not replace the v4.4 ToolRegistry, authenticated Remote sessions, laptop-local Remote policy, emergency stop, device-bridge executor/agent, configured filesystem roots, or Windows/UAC boundaries.
