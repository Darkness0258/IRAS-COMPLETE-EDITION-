# IRAS v4.4.0 RC1 — Persistent Autonomous Work + Provider Health

This release builds on v4.3 RC8. It does not weaken any Remote/session, bridge-root, emergency-stop, or permission boundary.

## Provider health

The web UI adds a **Providers** panel backed by `GET /v1/providers/status`. Cloud providers expose ONLINE, RATE LIMITED, COOLDOWN, AUTH ERROR, QUOTA ERROR, or OFFLINE states with latency, cooldown, last error, last success, active/next routing markers, and fallback order. The paired Windows Ollama fallback is probed through a bounded read-only `local_llm_status` bridge action.

## Persistent autonomous jobs

Orchestration journals are now version 2 checkpoints. Completed tasks, final evidence, project identity, rollback metadata, and recent job events survive Render restarts. Any task that was in-flight at restart becomes `interrupted`; it is never replayed automatically. The run becomes `interrupted` with `resume_required=true`.

Resume with a fresh Remote session re-queues only interrupted/downstream blocked nodes and preserves succeeded nodes. **Retry Failed** similarly re-queues failed/blocked nodes without throwing away successful checkpoints.

## Rollback metadata

Engineering preflight records the verified Windows project root, latest Git log entry, and whether the working tree was clean. This is metadata for safe rollback planning; RC1 does not automatically execute destructive rollback commands.

## Protocol

Remote protocol remains `1`.
