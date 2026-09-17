# IRAS v4.3 RC3 — Result Delivery and Project Binding

RC3 fixes two real-device acceptance failures found after RC2.

## Main-chat result delivery

Autonomous multi-agent runs started from ordinary chat are still background jobs,
but the web client now watches the returned `orchestration_run_id` and posts the
terminal coordinator result into the main conversation automatically. Users no
longer need to open **Tasks** just to discover the result.

The watcher is idempotent, so the Tasks panel and main chat do not duplicate the
same terminal result.

## Verified outcome-aware run state

A coordinator must now begin its final result with one of:

- `OUTCOME: COMPLETE`
- `OUTCOME: INCOMPLETE`
- `OUTCOME: FAILED`

IRAS records this as `verified_outcome`. A graph whose workers technically
returned but whose coordinator says the objective is incomplete is reported as
`partial_failure`, not `succeeded`.

## Project-root binding

RC2 resolved a Windows project before starting an engineering graph, but an LLM
worker could still later call Git/file tools with placeholders such as `.` or
`IRAS`. RC3 makes the preflight root an execution boundary:

- relative project paths are resolved underneath the verified Windows root;
- common placeholders such as `.`/`IRAS` are rebound to that root;
- absolute project-tool paths outside the verified project are rejected before
  entering the device command queue.

This binding uses request-local context, so parallel runs cannot overwrite one
another's workspace.

The v4 remote protocol remains `1`.
