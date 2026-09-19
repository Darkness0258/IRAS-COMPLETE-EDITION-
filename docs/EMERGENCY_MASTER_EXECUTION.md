# IRAS RC3 Emergency Master Execution

Master Control is the owner-armed emergency/high-authority operating profile.

When active, IRAS replaces ordinary small workflow/task budgets with a high-capacity adaptive profile. The intent is that an authorized emergency task does **not** stop merely because it is long, complex, repetitive, expensive, or requires many tool calls.

## Owner-intent continuation policy

While Master Control is active, IRAS receives this execution rule:

> Continue the authorized task until it is verified complete or a concrete blocker exists. Do not stop merely because of ordinary step/task budgets, complexity, length, cost, or recoverable tool failures. Re-plan and retry safe alternatives when useful. Never fabricate success.

This is deliberately **not** an unconditional “never refuse anything” instruction. The following remain non-bypassable:

- IRAS emergency stop;
- authentication and Remote-session validity;
- Windows/UAC/account and service authorization boundaries;
- configured filesystem/device boundaries;
- audit logging and verification requirements;
- applicable safety/security restrictions.

## Default emergency budgets

These defaults are intentionally much larger than normal mode and may be tuned locally:

- `IRAS_MASTER_AGENT_STEPS=256`
- `IRAS_MASTER_RUNTIME_SECONDS=21600` (6-hour runaway watchdog)
- `IRAS_MASTER_PARALLEL_TASKS=128`
- `IRAS_MASTER_ORCHESTRATION_TASKS=128`
- `IRAS_MASTER_ACTIVE_RUNS=32`
- `IRAS_MASTER_PROVIDER_WAIT_SECONDS=86400`
- `IRAS_MASTER_RECOVERY_ATTEMPTS=24`

The watchdog is not an ordinary task budget; it exists to stop a broken provider/tool loop from running forever. Persistent Master Control removes the session-expiry timer, not these hard safety/reliability boundaries.

## Persistent emergency session

```powershell
iras --master-enable 30 --master-persistent
```

Disable immediately with:

```powershell
iras --master-disable
```

The emergency stop always wins:

```powershell
iras --emergency-stop
```
