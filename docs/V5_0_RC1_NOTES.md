# IRAS v5.0.0 RC1 — Autonomous Personal Operating Layer

v5 keeps the proven v4.4 permissioned device bridge as the enforcement boundary and adds a modular higher-level autonomy layer.

## Integrated capability systems

1. Persistent scheduled autonomy with SQLite/PostgreSQL state.
2. Proactive change/health monitoring with transition-only notifications.
3. UIA + OmniParser visual scene fusion with conservative actionable targeting.
4. Dedicated Playwright browser agent with persistent auth state support.
5. Workflow recording and replay.
6. Durable semantic project/task memory.
7. Project knowledge graph for code, dependencies, API routes, tests, DB tables, and deploy files.
8. Isolated Git worktree coding workspaces; merging remains approval-controlled.
9. Self-healing recovery strategies with bounded learned success statistics.
10. Capability learning via proposal -> sandbox test -> explicit install approval.
11. First-class connector manifests for Gmail, Calendar, Drive, GitHub, Supabase, Discord, Slack, and Notion.
12. Full-duplex voice coordination with barge-in plus pluggable VAD/speaker/prosody analysis.
13. Mobile companion event/approval queue.
14. Notification center for browser/mobile/desktop adapters.
15. Artifact engine for DOCX, PDF, XLSX, PPTX, and ZIP bundles.
16. Secure named-secret vault: DPAPI on Windows or AES-GCM with an explicit server master key.
17. Docker-first sandbox execution with network disabled; local fallback is opt-in only.
18. Parallel autonomous research dossier engine.
19. Proposal/challenge/test/coordinator debate workflow.
20. Resource-aware provider/model selection.
21. Multi-checkpoint Git rollback timeline.
22. Activity/audit dashboard summaries.
23. Signed skill marketplace package format with Ed25519 verification.
24. Restricted home/network adapter framework with IP allowlists and approval for state changes.
25. Multi-user profiles with separate memory namespaces and permissions.
26. End-to-end AES-GCM encrypted sync bundles.
27. Goal -> project -> milestone -> job -> task hierarchy.

## Safety principles

- v5 does not bypass the v4.4 ToolRegistry, Remote session, bridge roots, local policy, or emergency stop.
- Scheduled autonomy is read-only by default; state-changing work still needs the normal authorization path.
- Learned capabilities never self-install. Installation requires sandbox success and explicit approval.
- Home/network integration performs no automatic scanning and is restricted to configured networks/adapters.
- The secrets vault exposes symbolic references to agents, not secret values.
- Git workspaces isolate coding changes and never auto-merge.
