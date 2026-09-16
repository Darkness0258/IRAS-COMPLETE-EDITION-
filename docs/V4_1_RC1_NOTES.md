# IRAS v4.1.0 RC1 — Multitasking

IRAS v4.1 RC1 adds bounded parallel task execution on top of the accepted v4.0.0 production baseline. The remote wire protocol remains `1`; existing paired Windows bridges remain compatible.

## Added

- Parallel task supervisor with a bounded worker pool (default 4 workers).
- Per-run task state: queued, running, succeeded, failed, or cancelled-before-start.
- Isolated conversation memory for sibling tasks so partial outputs cannot bleed across workers.
- Fresh provider + permission engine per worker.
- Request-local remote session **and device** provenance using `ContextVar`.
- `/v1/multitask/runs` create/status/cancel API.
- Web **Tasks** panel for 2–8 jobs.
- Explicit chat syntax: `/parallel task A || task B || task C`.
- `/ready` reports multitasking worker/cap configuration.

## Safety / concurrency model

Multitasking does not grant additional permissions. Each worker starts with the same cloud safe-action default and can only inherit a validated short-lived remote session. The laptop's local `RemoteAccessPolicy` and controller emergency stop remain final gates. Remote target device identity no longer depends on a mutable global `preferred_device_id`; it is bound to the executing request context.

The cloud may perform independent model, web, API, memory, and read-only work concurrently. Commands sent to one Windows bridge remain queued and executed by the device agent in order. This avoids concurrent mouse/keyboard races while still allowing the cloud reasoning/research portions of multiple tasks to overlap.

## RC1 acceptance checklist

1. `run-v410-validation.ps1` passes.
2. Render `/health` reports `version=4.1.0-rc1` and `remote_protocol=1`.
3. `/ready` reports multitasking enabled with the configured worker cap.
4. Run three independent non-device tasks from **Tasks** and verify their execution overlaps.
5. Run two Windows tasks in the same batch and verify both finish without UI corruption.
6. With emergency stop active, a parallel Windows action must fail closed exactly like a normal chat action.
7. Test two simultaneous remote sessions (when two paired devices are available) and verify commands remain bound to the correct device.

Do not promote v4.1.0 final until these real hosted/device checks pass. v4.0.0 remains the rollback-safe production baseline.
