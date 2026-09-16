# IRAS v4.2.0 RC5 — Autonomous chat execution

RC5 removes the need to manually choose `/parallel`, `/goal`, or the Tasks panel for normal work.

## Automatic execution routing

Normal chat now passes through a local provider-independent execution router before an LLM is called. The router chooses conservatively between:

- **Direct** for conversation and single actions.
- **Deterministic** for narrow exact-file write/verify/review workflows.
- **Parallel** for clearly independent jobs.
- **Multi-agent orchestration** for dependent implementation/test/review workflows.

Explicit `/parallel`, `/multitask`, `/goal`, `/orchestrate`, and `/agents` commands remain manual overrides.

Automatic parallel jobs are converted into an independent orchestration graph, so they inherit v4.2 provider-cooldown waiting, role isolation, pause/cancel lifecycle, and final synthesis instead of failing immediately when the provider pool cools down.

## Remote authorization handoff

IRAS still never grants itself Windows authority. Exact deterministic state changes require a live Remote session. RC5 improves the handoff by:

- prompting for Remote authorization before an exact-file chat or Tasks goal is submitted;
- validating browser-stored Remote-session expiry;
- refusing deterministic state-changing orchestration at the API boundary when no live Remote session is supplied;
- preserving the same request-local Remote session inside automatic parallel and multi-agent workers.

The laptop's local RemoteAccessPolicy and emergency stop remain authoritative.

## Configuration

- `IRAS_AUTONOMOUS_EXECUTION=true` enables automatic chat routing (default).
- `IRAS_AUTONOMOUS_WAIT_TIMEOUT=600` bounds synchronous automatic parallel waits.
- Remote protocol remains `1`.
