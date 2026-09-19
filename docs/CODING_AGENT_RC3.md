# IRAS RC3 Dedicated Coding Agent

IRAS RC3 now includes a first-class Coding Agent for repository-scale engineering work. Quick Code remains the deterministic path for tiny one-file requests; the Coding Agent handles multi-file implementation, debugging, testing, repair, and final review.

## Execution graph

A Coding Agent run uses a fixed engineering DAG:

1. inspect the resolved project and Git baseline;
2. implement the requested change;
3. run targeted tests/diagnostics;
4. repair failures when needed, or avoid gratuitous edits when tests already pass;
5. run final verification;
6. review the diff, correctness, security, and regression risk;
7. coordinator synthesizes the verified outcome.

The repair node is allowed to run after failed tests so a failed test does not terminate the job before the agent gets a chance to fix it.

## Permissioned Windows control

The Coding Agent can use Windows controls when they materially help engineering work:

- open/focus VS Code and the resolved project;
- observe UI through Windows UI Automation and managed OmniParser;
- perform grounded computer actions from fresh observations;
- use semantic UI actions and the VS Code integrated terminal;
- inspect/copy clipboard data subject to the normal permission engine;
- list processes for diagnostics;
- use bounded project file, Git, test, Quick Code, and project-discovery tools;
- call `device_run_command` only when the active permission context permits CRITICAL command execution. This command remains `shell=False` with explicit executable/argv handling.

The Coding Agent does **not** get default power control, arbitrary process termination, or delete-path capability in its role toolset.

All Windows actions still pass through the existing ToolRegistry permission engine, Remote session permission level, laptop-side Remote policy, configured filesystem roots, emergency stop, audit log, and Windows/UAC/account boundaries. No protected Remote/device enforcement file is weakened by this feature.

## Cloud / Web / Android

Cloud exposes:

- `GET /v1/coding-agent/status`
- `POST /v1/coding-agent/runs`
- `GET /v1/coding-agent/runs/{run_id}`

A Cloud Coding Agent run requires a live IRAS Remote session because it may edit Windows project state. A verified Master session can provide CRITICAL authority, including `device_run_command`, while ordinary lower-permission sessions remain capped normally.

Normal chat also routes clear engineering objectives to the dedicated Coding Agent automatically. `/code <goal>` forces Coding Agent mode explicitly and works from the Windows cloud client; Web/Android can send the same `/code ...` chat command through the shared Cloud API.

Examples:

```text
/code fix the login bug in D:\Projects\MyApp and run the tests
/code refactor the API module in my IRAS project, repair regressions, and verify the diff
```

Windows cloud client status:

```text
/code status
```

## Local desktop / CLI

Local desktop and CLI also accept:

```text
/code <goal>
/code status
```

Local background Coding Agent execution requires Master Control with autonomous mode enabled. This is deliberate: local background workers otherwise remain READ-capped and cannot silently inherit interactive state-changing permissions.

## Safety and verification behavior

The Coding Agent prefers deterministic file/Git/test tools over GUI typing, inspects before editing, verifies Git state/diff after changes, and must not treat a permission failure as something to bypass. Emergency stop remains authoritative at all times.
