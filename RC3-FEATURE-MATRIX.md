# IRAS v5.0.0 RC3 — Complete Feature Matrix

RC3 declares **34 operating-layer feature families**. A feature is counted here only when the implementation is present, reachable through an IRAS control surface, protected by the existing permission/security model where state can change, and covered by local contract/regression tests.

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
| 9 | Isolated coding workspaces | Git worktrees, status/diff/commits/tests/commit/merge-plan/approval-gated merge/remove |
| 10 | Self-healing workflows | Recovery statistics and bounded recovery hooks without replaying consequential actions |
| 11 | Capability learning | Proposal, sandbox qualification, install inventory and uninstall lifecycle |
| 12 | Plugin connector layer | Gmail/Calendar/Drive/GitHub/Supabase/Slack/Discord/Notion lifecycle, vault refs, expiry fail-closed |
| 13 | Full-duplex voice runtime | VAD/STT/TTS coordinator, wake state and barge-in cancellation surface |
| 14 | Mobile companion hub | Device registry, heartbeat, event delivery/ACK and approval queue |
| 15 | Android companion | Existing chat/voice plus RC3 registration, event polling, notifications and approve/deny UI |
| 16 | Notification system | Browser/mobile/desktop event persistence and read state |
| 17 | Artifact engine | DOCX, PDF, XLSX, PPTX and bundle generation/listing |
| 18 | Secure secrets vault | Symbolic refs only; DPAPI on Windows / AES-GCM master-key mode elsewhere |
| 19 | Sandbox execution | Docker-first no-network Python execution; local fallback remains explicit opt-in |
| 20 | Autonomous research projects | Orchestrated research/review task graph with local READ-capped workers |
| 21 | Agent debate review | Proposal/challenge/test orchestration with bounded worker roles |
| 22 | Resource-aware intelligence | Resource/provider routing surface with local-safe fallback paths |
| 23 | Rollback timeline | Git checkpoint capture, preview and approval-gated restore |
| 24 | Activity/audit dashboard | Filtered audit summary/rows plus Control Center display |
| 25 | Signed skill marketplace | Ed25519 signature over manifest **and every installed file hash**, verify/install/uninstall |
| 26 | Home network adapters | Fixed allowlist, no ambient scanning, read status and approval-gated state changes |
| 27 | Multi-user profiles | Create/update/list permission namespaces |
| 28 | Encrypted sync | AES-GCM profile/memory bundles using vault-referenced keys and sync journal |
| 29 | Goal hierarchy | Goal/project/milestone/job/task tree, dependencies, readiness and progress roll-up |
| 30 | Schema migrations | Persistent migration ledger and indexed RC3 schema upgrades |
| 31 | Control Center UI | Feature matrix plus autonomy/artifact/recovery/capability/home/migration status |
| 32 | Unified cloud workspace | Restart-safe client presence, shared active thread/history/preferences across Windows cloud client, web/PWA and Android |
| 33 | Master Control | Local owner-elevation with CRITICAL registered-tool authority, Emergency Adaptive high-capacity execution, shell/power opt-in, cloud/web/mobile attachment only after local arming, emergency-stop/audit preservation |
| 34 | Release engineering | Clean-tree/integrated validators, deterministic package builder and release manifest |

## Preserved enforcement boundary

Remote protocol remains **1**. The v4.4 ToolRegistry, Remote authorization, emergency-stop runtime, device-bridge executor/agent and bridge-root restrictions remain the authoritative enforcement layer. RC3 operating-layer features do not bypass them.

## Build-first acceptance

The RC3 regression and integrated acceptance path uses local mocks/fixtures/Ollama-safe construction and does not require quota-consuming cloud-model calls. Real third-party accounts, Android hardware, Docker availability, and the Windows OmniParser model stack are host/runtime integrations and are checked fail-closed when used.
