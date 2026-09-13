# IRAS v3.3.0 — Autonomous Workflow Engine

v3.2 gave IRAS semantic computer observation and bounded UI actions.

v3.3 upgrades the agent loop so a request is handled as one goal rather than a
sequence of unrelated tool calls.

## Control loop

For planner-mode device tasks IRAS now follows:

```text
PLAN
→ EXECUTE
→ INSPECT REAL TOOL RESULT
→ VERIFY
→ ADAPT / RECOVER
→ FINISH
```

The private plan is never exposed as chain-of-thought. The user receives only
useful progress/results.

## Longer but bounded workflows

Normal IRAS turns keep the existing `max_steps=8`.

Only bounded autonomous device workflows get a larger execution budget:

```text
minimum planner budget: 12
maximum planner budget: 16
```

This is enough for tasks such as:

```text
open Notepad
→ observe
→ find editor
→ type text
→ re-observe
→ verify
```

or:

```text
open Discord
→ observe
→ search contact
→ inspect results
→ open chat
→ observe
→ target message box
→ type
→ verify
```

without creating an unbounded loop.

## Recovery

v3.3 tracks real tool outcomes.

If a tool fails, the model is explicitly told to inspect the error and change
approach. The same failed call cannot be repeated forever: after two identical
failed attempts, IRAS blocks a third unchanged attempt and forces re-observation
or a different safe route.

Three consecutive failures trigger stronger recovery guidance.

## Verification

IRAS tracks when a state-changing action still needs proof.

Examples that normally require a follow-up check:

```text
device_interact_app
device_app_control
unverified app launch
```

`device_observe_ui` clears pending GUI verification.

`device_semantic_action` counts as verified when its built-in re-observation
returns `verification_observation`.

IRAS will not voluntarily end a planner workflow with a success claim while
the tracker says the last uncertain state change remains unverified.

## Safety

v3.3 adds no new privileged capability.

It does not expose:

```text
arbitrary shell
cmd
PowerShell chosen by the model
registry/admin automation
permission bypass
unbounded tool loops
```

All actions still use the existing ToolRegistry, permission engine, app-scope
guard, device bridge and audit log.
