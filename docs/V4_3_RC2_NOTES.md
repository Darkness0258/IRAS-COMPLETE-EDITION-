# IRAS v4.3 RC2 — Project-Aware Engineering Reliability

RC2 fixes the real-device acceptance failure where autonomous engineering agents guessed a project path outside `IRAS_BRIDGE_ROOTS`, then later lost the device during verification.

## Changes

- Adds read-only bounded `find_projects` / `device_find_projects` repository discovery inside configured bridge roots.
- Engineering orchestration preflight verifies the Remote target device is online, resolves the requested Windows project, and validates Git access before starting the DAG.
- The verified `project_root` is propagated through request-local orchestration context and injected into every specialized worker.
- Ambiguous project discovery fails early instead of selecting an arbitrary repository.
- Exact-file deterministic goals bypass project discovery because their target path is already explicit.
- Temporary device offline/command-timeout conditions use a separate bounded backpressure wait without consuming task retries. Root/permission errors are never treated as transient.
- Tasks UI shows device-wait countdowns.
- Remote protocol remains `1`.

## Default

`IRAS_ORCHESTRATION_DEVICE_WAIT_SECONDS=180` (bounded `0..900`).
